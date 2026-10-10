"""Scoring logic for opportunities"""

from app.models.signal import Signal
from app.models.domain import Domain
from app.core.signal_importance import resolve_signal_importance


class Scorer:
    """Score opportunities based on signals and profile"""

    SCORE_WEIGHTS = {
        "jobs": 40,  # Priority #1 - Hiring indicates growth
        "pricing_change": 35,  # Priority #2 - Pricing changes indicate business evolution (slightly boosted)
        "tool_added": 20,  # Priority #3 - New tools indicate tech stack evolution
        "new_product": 35,  # New products indicate expansion/innovation
        "partnership": 25,  # Partnerships indicate business development
        "expansion": 30,  # Geographic expansion indicates growth
        "funding": 40,  # Funding indicates significant growth potential
        "new_site": 10,  # New site indicates rebranding/relaunch
        "page_redesign": 22,  # Significant content change without explicit business signal
        "recent_activity": 15,  # Content update, weak buying intent
        "minor_activity": 8,  # Minor tweak, activity hint only
    }

    IMPORTANCE_CAP = {
        "weak": 25,
        "medium": 45,
        "strong": 100,
    }

    FRESHNESS_BONUS = 10  # If detected < 7 days ago

    async def score(self, signal: Signal, domain: Domain) -> int:
        """Calculate score for a signal (0-100)"""
        base_score = self.SCORE_WEIGHTS.get(signal.type, 0)

        payload = signal.payload_json or {}

        # Extra intelligence for pricing changes
        if signal.type == "pricing_change":
            price_info = payload.get("price_change") or {}
            if price_info.get("has_price_change"):
                # Any explicit numeric price change gets a bonus
                base_score += 10

                # If the max increase is large relative to previous prices, boost more
                old_prices = price_info.get("old_prices") or []
                max_increase = float(price_info.get("max_increase") or 0.0)
                if old_prices and max_increase > 0:
                    avg_old = sum(old_prices) / len(old_prices)
                    if avg_old > 0:
                        relative_change = max_increase / avg_old
                        # >20% increase: strong signal
                        if relative_change >= 0.2:
                            base_score += 10
                        # >50%: very strong signal (cap will still apply later)
                        if relative_change >= 0.5:
                            base_score += 10

        # Extra intelligence for job intensity (actively / urgently hiring)
        if signal.type == "jobs":
            keywords_found = payload.get("keywords_found") or []
            intensity_keywords = [
                "activement",
                "urgemment",
                "immédiatement",
                "dès maintenant",
                "actively hiring",
                "urgently hiring",
                "immediately hiring",
            ]
            if any(kw in keywords_found for kw in intensity_keywords):
                base_score += 10

        # Add freshness bonus
        from datetime import datetime, timedelta

        if signal.detected_at:
            days_old = (datetime.utcnow() - signal.detected_at).days
            if days_old < 7:
                base_score += self.FRESHNESS_BONUS

        # Plafond selon l'importance du signal
        importance = resolve_signal_importance(signal.type, payload)
        if importance in self.IMPORTANCE_CAP:
            base_score = min(base_score, self.IMPORTANCE_CAP[importance])

        return min(100, base_score)
