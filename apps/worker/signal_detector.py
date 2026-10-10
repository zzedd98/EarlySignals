"""Signal detection logic"""

import re
from typing import List, Optional
from datetime import datetime

from app.models.snapshot import DomainSnapshot
from app.models.signal import Signal

from change_analyzer import ChangeAnalyzer


class SignalDetector:
    """Detect signals from snapshots - all B2B relevant signals"""

    # Jobs/Careers keywords (Priority #1)
    JOB_KEYWORDS = [
        # French
        "recrutement",
        "recruitment",
        "recrute",
        "recrutons",
        "nous recrutons",
        "on recrute",
        "rejoignez-nous",
        "rejoignez nous",
        "nous embauchons",
        "embauche",
        "embauches",
        "emploi",
        "emplois",
        "carrière",
        "carrières",
        "poste",
        "postes",
        "offre d'emploi",
        "offres d'emploi",
        "candidature",
        "candidater",
        "candidat",
        "candidats",
        "opportunité",
        "opportunités",
        "poste à pourvoir",
        "postes à pourvoir",
        "vacance",
        "vacances de poste",
        # English
        "hiring",
        "jobs",
        "careers",
        "career",
        "join us",
        "join our team",
        "we are hiring",
        "we're hiring",
        "we hire",
        "open positions",
        "job opening",
        "job openings",
        "position",
        "positions",
        "apply",
        "application",
        "applicant",
        "applicants",
        "opportunity",
        "opportunities",
        "job vacancy",
        "job vacancies",
        "vacancy",
        "vacancies",
    ]

    # Pricing keywords (Priority #2)
    PRICING_KEYWORDS = [
        # French
        "pricing",
        "tarif",
        "tarifs",
        "prix",
        "plan",
        "plans",
        "forfait",
        "forfaits",
        "abonnement",
        "abonnements",
        "facturation",
        "billing",
        "devis",
        "devis gratuit",
        "offre",
        "offres",
        "subscription",
        "subscriptions",
        # English
        "pricing",
        "price",
        "prices",
        "plan",
        "plans",
        "package",
        "packages",
        "subscription",
        "subscriptions",
        "billing",
        "quote",
        "free quote",
    ]

    # Product/Service keywords
    PRODUCT_KEYWORDS = [
        # French
        "nouveau produit",
        "nouveaux produits",
        "nouvelle fonctionnalité",
        "fonctionnalités",
        "nouvelle solution",
        "solutions",
        "service",
        "services",
        "produit",
        "produits",
        "lancement",
        "lancé",
        "release",
        "released",
        "feature",
        "features",
        "fonctionnalité",
        # English
        "new product",
        "new products",
        "new feature",
        "new features",
        "product launch",
        "launch",
        "launched",
        "release",
        "released",
        "solution",
        "solutions",
        "service",
        "services",
        "product",
        "products",
    ]

    # Partnership keywords
    PARTNERSHIP_KEYWORDS = [
        # French
        "partenaire",
        "partenaires",
        "partenariat",
        "partenariats",
        "collaboration",
        "collaborations",
        "partenaires stratégiques",
        "nouveau partenaire",
        "nouveaux partenaires",
        # English
        "partner",
        "partners",
        "partnership",
        "partnerships",
        "collaboration",
        "collaborations",
        "strategic partner",
        "strategic partners",
        "new partner",
        "new partners",
        "partner with",
        "partnering with",
    ]

    # Expansion keywords
    EXPANSION_KEYWORDS = [
        # French
        "ouverture",
        "ouvertures",
        "expansion",
        "expansions",
        "nouveau bureau",
        "nouveaux bureaux",
        "nouvelle ville",
        "nouveau pays",
        "implantation",
        "implantations",
        "s'étendre",
        "développement",
        "nouvelle implantation",
        "nouvelle localisation",
        # English
        "opening",
        "openings",
        "expansion",
        "expansions",
        "new office",
        "new offices",
        "new location",
        "new locations",
        "new city",
        "new country",
        "expanding",
        "expanded",
        "geographic expansion",
        "market expansion",
    ]

    # Funding keywords
    FUNDING_KEYWORDS = [
        # French
        "levée de fonds",
        "levée de fond",
        "financement",
        "investissement",
        "investisseur",
        "investisseurs",
        "série a",
        "série b",
        "série c",
        "seed",
        "round",
        "financement",
        "capital",
        "fonds",
        # English
        "funding",
        "fundraise",
        "fundraising",
        "investment",
        "investor",
        "investors",
        "series a",
        "series b",
        "series c",
        "seed round",
        "round",
        "raised",
        "raising",
        "venture capital",
        "vc",
        "angel",
        "angel investor",
        "backed by",
    ]

    # B2B Tools detection
    TOOLS = {
        "stripe": ["stripe.com", "js.stripe.com"],
        "intercom": ["intercom.io", "widget.intercom.io"],
        "crisp": ["crisp.chat"],
        "hubspot": ["hubspot.com", "js.hubspot.com"],
        "meta_pixel": ["facebook.com/tr", "connect.facebook.net"],
        "google_ads": ["googletagmanager.com", "google-analytics.com"],
        "segment": ["segment.io", "cdn.segment.com"],
        "shopify": ["shopify.com", "cdn.shopify.com"],
        "salesforce": ["salesforce.com", "force.com"],
        "zendesk": ["zendesk.com", "zdassets.com"],
        "mixpanel": ["mixpanel.com"],
        "amplitude": ["amplitude.com"],
        "hotjar": ["hotjar.com"],
        "datadog": ["datadoghq.com"],
        "sentry": ["sentry.io"],
        "mailchimp": ["mailchimp.com", "list-manage.com"],
        "sendgrid": ["sendgrid.com"],
        "twilio": ["twilio.com"],
        "algolia": ["algolia.net", "algolia.com"],
    }

    async def detect(
        self,
        snapshot: DomainSnapshot,
        previous_snapshot: Optional[DomainSnapshot] = None,
        change_analysis: Optional[dict] = None,
    ) -> List[Signal]:
        """
        Detect all B2B signals from a snapshot.

        If previous_snapshot is provided, only detects signals for NEW content
        (keywords that appear in the new snapshot but not in the old one).
        This prevents false positives from static content.
        """
        signals = []

        if not snapshot.html_text:
            return signals

        html_lower = snapshot.html_text.lower()
        url = snapshot.url.lower()

        added_text = ""
        is_significant_change = True
        price_change_info = None

        if change_analysis is not None:
            is_significant_change = change_analysis.get("is_significant", True)
            added_text = (change_analysis.get("added_text") or "").lower()
            price_change_info = change_analysis.get("price_change", {})
        elif previous_snapshot and previous_snapshot.html_text:
            change_analyzer = ChangeAnalyzer()
            change_analysis = change_analyzer.analyze(
                previous_snapshot.html_text, snapshot.html_text
            )
            is_significant_change = change_analysis["is_significant"]
            added_text = change_analysis["added_text"].lower()
            price_change_info = change_analysis.get("price_change", {})

        if (
            previous_snapshot
            and previous_snapshot.html_text
            and change_analysis is not None
            and not is_significant_change
            and not change_analysis.get("has_price_change")
        ):
            return signals

        text_to_analyze = added_text if added_text else html_lower
        signals.extend(
            self._detect_business_signals(
                snapshot,
                previous_snapshot,
                text_to_analyze,
                html_lower,
                url,
                price_change_info,
            )
        )

        return signals

    def _detect_business_signals(
        self,
        snapshot: DomainSnapshot,
        previous_snapshot: Optional[DomainSnapshot],
        text_to_analyze: str,
        html_lower: str,
        url: str,
        price_change_info,
    ) -> List[Signal]:
        """Détecte les signaux métier forts (recrutement, tarifs, etc.)."""
        signals: List[Signal] = []

        # 1. Detect jobs signal (Priority #1)
        # Only detect if keyword appears in NEW content (or if no previous snapshot)
        job_keywords_found = [
            kw for kw in self.JOB_KEYWORDS if kw in text_to_analyze or kw in url
        ]
        if job_keywords_found:
            # If we have previous snapshot, check if these keywords were already there
            if previous_snapshot and previous_snapshot.html_text:
                prev_html_lower = previous_snapshot.html_text.lower()
                # Only create signal if keyword appears in NEW content but not in old
                new_job_keywords = [
                    kw for kw in job_keywords_found if kw not in prev_html_lower
                ]
                if new_job_keywords or any(kw in url for kw in job_keywords_found):
                    signals.append(
                        Signal(
                            domain_id=snapshot.domain_id,
                            type="jobs",
                            proof_url=snapshot.url,
                            detected_at=datetime.utcnow(),
                            payload_json={
                                "snapshot_id": str(snapshot.id),
                                "keywords_found": new_job_keywords,
                                "detected_via": (
                                    "new_content" if new_job_keywords else "url_change"
                                ),
                            },
                        )
                    )
            else:
                # No previous snapshot - detect based on current content
                signals.append(
                    Signal(
                        domain_id=snapshot.domain_id,
                        type="jobs",
                        proof_url=snapshot.url,
                        detected_at=datetime.utcnow(),
                        payload_json={"snapshot_id": str(snapshot.id)},
                    )
                )

        # 2. Detect pricing change (Priority #2)
        # Check URL path
        pricing_paths = [
            "/pricing",
            "/plans",
            "/offer",
            "/tarifs",
            "/prix",
            "/forfaits",
            "/abonnement",
        ]
        has_pricing_url = any(path in url for path in pricing_paths)

        # Check content keywords in NEW content
        pricing_keywords_found = [
            kw for kw in self.PRICING_KEYWORDS if kw in text_to_analyze
        ]
        has_pricing_content = len(pricing_keywords_found) > 0

        # Detect explicit numerical price changes (even if text diff is tiny)
        has_explicit_price_change = bool(
            price_change_info and price_change_info.get("has_price_change")
        )

        if has_pricing_url or has_pricing_content or has_explicit_price_change:
            # If we have previous snapshot, verify it's a new pricing page, new pricing content
            # OR an actual numeric price change
            if previous_snapshot:
                prev_url = previous_snapshot.url.lower()
                prev_has_pricing_url = any(path in prev_url for path in pricing_paths)
                prev_has_pricing_content = any(
                    kw in previous_snapshot.html_text.lower()
                    for kw in self.PRICING_KEYWORDS
                )

                should_create_pricing_signal = False
                detected_via: str = "content"

                # New pricing page in URL
                if has_pricing_url and not prev_has_pricing_url:
                    should_create_pricing_signal = True
                    detected_via = "url"

                # New pricing content (keywords) that wasn't there before
                if has_pricing_content and not prev_has_pricing_content:
                    should_create_pricing_signal = True
                    detected_via = "content"

                # Or explicit numeric price change (even if URL/keywords were already there)
                if has_explicit_price_change:
                    should_create_pricing_signal = True
                    detected_via = "price_change"

                if should_create_pricing_signal:
                    signals.append(
                        Signal(
                            domain_id=snapshot.domain_id,
                            type="pricing_change",
                            proof_url=snapshot.url,
                            detected_at=datetime.utcnow(),
                            payload_json={
                                "snapshot_id": str(snapshot.id),
                                "detected_via": detected_via,
                                "price_change": (
                                    price_change_info if price_change_info else None
                                ),
                            },
                        )
                    )
            else:
                # No previous snapshot - detect based on current content
                signals.append(
                    Signal(
                        domain_id=snapshot.domain_id,
                        type="pricing_change",
                        proof_url=snapshot.url,
                        detected_at=datetime.utcnow(),
                        payload_json={
                            "snapshot_id": str(snapshot.id),
                            "detected_via": "url" if has_pricing_url else "content",
                            "price_change": (
                                price_change_info if price_change_info else None
                            ),
                        },
                    )
                )

        # 3. Detect new products/services
        # Look for strong indicators of new product launches in NEW content
        product_indicators = [
            "nouveau produit",
            "new product",
            "nouvelle solution",
            "new solution",
            "lancement",
            "launch",
            "lancé",
            "launched",
            "nouvelle fonctionnalité",
            "new feature",
            "release",
            "released",
        ]
        product_indicators_found = [
            ind for ind in product_indicators if ind in text_to_analyze
        ]

        if product_indicators_found:
            # Additional check: ensure it's not just a generic product page
            product_url_paths = [
                "/products",
                "/produits",
                "/solutions",
                "/features",
                "/fonctionnalites",
            ]
            has_product_url = any(path in url for path in product_url_paths)
            has_strong_product_content = any(
                keyword in text_to_analyze for keyword in self.PRODUCT_KEYWORDS
            )

            if has_product_url or has_strong_product_content:
                # Only signal if it's NEW (wasn't in previous snapshot)
                if previous_snapshot and previous_snapshot.html_text:
                    prev_html_lower = previous_snapshot.html_text.lower()
                    prev_has_indicators = any(
                        ind in prev_html_lower for ind in product_indicators
                    )
                    prev_has_content = any(
                        kw in prev_html_lower for kw in self.PRODUCT_KEYWORDS
                    )

                    # Only create signal if indicators are NEW
                    if not prev_has_indicators and not prev_has_content:
                        signals.append(
                            Signal(
                                domain_id=snapshot.domain_id,
                                type="new_product",
                                proof_url=snapshot.url,
                                detected_at=datetime.utcnow(),
                                payload_json={"snapshot_id": str(snapshot.id)},
                            )
                        )
                else:
                    # No previous snapshot
                    signals.append(
                        Signal(
                            domain_id=snapshot.domain_id,
                            type="new_product",
                            proof_url=snapshot.url,
                            detected_at=datetime.utcnow(),
                            payload_json={"snapshot_id": str(snapshot.id)},
                        )
                    )

        # 4. Detect partnerships (only if NEW)
        partnership_url_paths = [
            "/partners",
            "/partenaires",
            "/partnership",
            "/partenariat",
        ]
        has_partnership_url = any(path in url for path in partnership_url_paths)
        has_partnership_content = any(
            keyword in text_to_analyze for keyword in self.PARTNERSHIP_KEYWORDS
        )

        if has_partnership_url or has_partnership_content:
            if previous_snapshot:
                prev_url = previous_snapshot.url.lower()
                prev_has_url = any(path in prev_url for path in partnership_url_paths)
                prev_has_content = any(
                    kw in previous_snapshot.html_text.lower()
                    for kw in self.PARTNERSHIP_KEYWORDS
                )

                # Only signal if partnership content is NEW
                if (has_partnership_url and not prev_has_url) or (
                    has_partnership_content and not prev_has_content
                ):
                    signals.append(
                        Signal(
                            domain_id=snapshot.domain_id,
                            type="partnership",
                            proof_url=snapshot.url,
                            detected_at=datetime.utcnow(),
                            payload_json={
                                "snapshot_id": str(snapshot.id),
                                "detected_via": (
                                    "url" if has_partnership_url else "content"
                                ),
                            },
                        )
                    )
            else:
                signals.append(
                    Signal(
                        domain_id=snapshot.domain_id,
                        type="partnership",
                        proof_url=snapshot.url,
                        detected_at=datetime.utcnow(),
                        payload_json={
                            "snapshot_id": str(snapshot.id),
                            "detected_via": "url" if has_partnership_url else "content",
                        },
                    )
                )

        # 5. Detect expansions (only if NEW)
        expansion_url_paths = [
            "/expansion",
            "/ouverture",
            "/opening",
            "/new-office",
            "/nouveau-bureau",
        ]
        has_expansion_url = any(path in url for path in expansion_url_paths)
        has_expansion_content = any(
            keyword in text_to_analyze for keyword in self.EXPANSION_KEYWORDS
        )

        if has_expansion_url or has_expansion_content:
            if previous_snapshot:
                prev_url = previous_snapshot.url.lower()
                prev_has_url = any(path in prev_url for path in expansion_url_paths)
                prev_has_content = any(
                    kw in previous_snapshot.html_text.lower()
                    for kw in self.EXPANSION_KEYWORDS
                )

                # Only signal if expansion content is NEW
                if (has_expansion_url and not prev_has_url) or (
                    has_expansion_content and not prev_has_content
                ):
                    signals.append(
                        Signal(
                            domain_id=snapshot.domain_id,
                            type="expansion",
                            proof_url=snapshot.url,
                            detected_at=datetime.utcnow(),
                            payload_json={
                                "snapshot_id": str(snapshot.id),
                                "detected_via": (
                                    "url" if has_expansion_url else "content"
                                ),
                            },
                        )
                    )
            else:
                signals.append(
                    Signal(
                        domain_id=snapshot.domain_id,
                        type="expansion",
                        proof_url=snapshot.url,
                        detected_at=datetime.utcnow(),
                        payload_json={
                            "snapshot_id": str(snapshot.id),
                            "detected_via": "url" if has_expansion_url else "content",
                        },
                    )
                )

        # 6. Detect funding (only if NEW)
        funding_url_paths = [
            "/funding",
            "/financement",
            "/investissement",
            "/investors",
            "/investisseurs",
        ]
        has_funding_url = any(path in url for path in funding_url_paths)
        has_funding_content = any(
            keyword in text_to_analyze for keyword in self.FUNDING_KEYWORDS
        )

        if has_funding_url or has_funding_content:
            if previous_snapshot:
                prev_url = previous_snapshot.url.lower()
                prev_has_url = any(path in prev_url for path in funding_url_paths)
                prev_has_content = any(
                    kw in previous_snapshot.html_text.lower()
                    for kw in self.FUNDING_KEYWORDS
                )

                # Only signal if funding content is NEW
                if (has_funding_url and not prev_has_url) or (
                    has_funding_content and not prev_has_content
                ):
                    signals.append(
                        Signal(
                            domain_id=snapshot.domain_id,
                            type="funding",
                            proof_url=snapshot.url,
                            detected_at=datetime.utcnow(),
                            payload_json={
                                "snapshot_id": str(snapshot.id),
                                "detected_via": "url" if has_funding_url else "content",
                            },
                        )
                    )
            else:
                signals.append(
                    Signal(
                        domain_id=snapshot.domain_id,
                        type="funding",
                        proof_url=snapshot.url,
                        detected_at=datetime.utcnow(),
                        payload_json={
                            "snapshot_id": str(snapshot.id),
                            "detected_via": "url" if has_funding_url else "content",
                        },
                    )
                )

        # 7. Detect tools (Priority #3) - only if tool appears NEW
        for tool_name, patterns in self.TOOLS.items():
            tool_found = any(pattern in html_lower for pattern in patterns)

            if tool_found:
                # Check if tool was already present in previous snapshot
                if previous_snapshot and previous_snapshot.html_text:
                    prev_html_lower = previous_snapshot.html_text.lower()
                    tool_was_present = any(
                        pattern in prev_html_lower for pattern in patterns
                    )

                    # Only signal if tool is NEW (wasn't there before)
                    if not tool_was_present:
                        signals.append(
                            Signal(
                                domain_id=snapshot.domain_id,
                                type="tool_added",
                                proof_url=snapshot.url,
                                detected_at=datetime.utcnow(),
                                payload_json={
                                    "tool": tool_name,
                                    "snapshot_id": str(snapshot.id),
                                },
                            )
                        )
                else:
                    # No previous snapshot - detect based on current content
                    signals.append(
                        Signal(
                            domain_id=snapshot.domain_id,
                            type="tool_added",
                            proof_url=snapshot.url,
                            detected_at=datetime.utcnow(),
                            payload_json={
                                "tool": tool_name,
                                "snapshot_id": str(snapshot.id),
                            },
                        )
                    )

        return signals
