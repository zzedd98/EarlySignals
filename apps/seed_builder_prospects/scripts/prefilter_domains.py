"""
Prefiltre offline de domaines (sans crawl HTTP) pour prioriser un CSV type Tranco.

Sorties (dans --out-dir):
- keep.csv    : domaines a garder en priorite
- review.csv  : domaines ambigus a verifier
- exclude.csv : domaines exclus
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class RuleConfig:
    hard_exclude_domains_contains: tuple[str, ...]
    hard_exclude_tokens: tuple[str, ...]
    positive_tokens: dict[str, int]
    negative_tokens: dict[str, int]
    soft_exclude_tokens: tuple[str, ...]


DEFAULT_RULES = RuleConfig(
    hard_exclude_domains_contains=(
        # Institutionnel / etatique
        "gouv.fr",
        "service-public.fr",
        "legifrance.gouv.fr",
        "ameli.fr",
        "urssaf.fr",
        "impots.gouv.fr",
        "caf.fr",
        # Plateformes globales
        "google.",
        "youtube.",
        "facebook.",
        "instagram.",
        "linkedin.",
        "x.com",
        "twitter.",
        "wikipedia.",
        "amazon.",
        "apple.",
        "microsoft.",
        # Infos / medias majeurs
        "lemonde.fr",
        "lefigaro.fr",
        "franceinfo.fr",
        "bfmtv.com",
        "ouest-france.fr",
        "20minutes.fr",
        "leparisien.fr",
        # Marketplaces / annuaires
        "leboncoin.fr",
        "pagesjaunes.fr",
    ),
    hard_exclude_tokens=(
        "gouv",
        "ministere",
        "prefecture",
        "mairie",
        "news",
        "journal",
        "presse",
        "media",
        "tv",
        "radio",
    ),
    positive_tokens={
        "b2b": 35,
        "saas": 30,
        "crm": 30,
        "erp": 28,
        "cloud": 24,
        "software": 24,
        "logiciel": 22,
        "solution": 20,
        "solutions": 20,
        "data": 16,
        "analytics": 16,
        "api": 14,
        "pro": 12,
        "business": 12,
        "entreprise": 12,
        "tech": 10,
        "digital": 8,
    },
    negative_tokens={
        "shop": -28,
        "store": -28,
        "boutique": -28,
        "market": -20,
        "deal": -16,
        "promo": -14,
        "voyage": -16,
        "travel": -16,
        "hotel": -16,
        "restaurant": -18,
        "pizza": -20,
        "recette": -15,
        "beauty": -16,
        "beaute": -16,
        "mode": -15,
        "blog": -10,
        "actu": -18,
        "news": -18,
    },
    soft_exclude_tokens=(
        "annuaire",
        "wiki",
        "forum",
        "torrent",
        "stream",
        "casino",
        "bet",
        "pari",
    ),
)


def normalize_domain(raw: str) -> str:
    value = (raw or "").strip().lower()
    value = value.replace("http://", "").replace("https://", "")
    if value.startswith("www."):
        value = value[4:]
    value = value.split("/", 1)[0].strip(".")
    return value


def extract_tokens(domain: str) -> list[str]:
    base = domain.split(".")[0]
    return [t for t in TOKEN_SPLIT_RE.split(base) if t]


def score_domain(domain: str, rules: RuleConfig) -> tuple[int, str, list[str]]:
    reasons: list[str] = []
    score = 0
    tokens = extract_tokens(domain)
    tld = domain.split(".")[-1] if "." in domain else ""

    # Hard excludes directs sur domaine complet
    for marker in rules.hard_exclude_domains_contains:
        if marker in domain:
            reasons.append(f"hard_exclude_domain:{marker}")
            return -999, "exclude", reasons

    # Hard excludes par token
    for token in tokens:
        if token in rules.hard_exclude_tokens:
            reasons.append(f"hard_exclude_token:{token}")
            return -999, "exclude", reasons

    # Soft excludes
    for token in tokens:
        if token in rules.soft_exclude_tokens:
            score -= 25
            reasons.append(f"soft_exclude:{token}(-25)")

    # Positifs / negatifs
    for token in tokens:
        if token in rules.positive_tokens:
            delta = rules.positive_tokens[token]
            score += delta
            reasons.append(f"+{token}({delta})")
        if token in rules.negative_tokens:
            delta = rules.negative_tokens[token]
            score += delta
            reasons.append(f"{token}({delta})")

    # Heuristiques structurelles
    if tld == "io":
        score += 6
        reasons.append("+tld_io(6)")
    elif tld == "fr":
        score += 2
        reasons.append("+tld_fr(2)")
    elif tld in {"org", "gov"}:
        score -= 20
        reasons.append("tld_non_commercial(-20)")

    if len(domain) <= 6:
        score -= 6
        reasons.append("short_domain(-6)")

    digits_count = sum(c.isdigit() for c in domain)
    if digits_count >= 3:
        score -= 8
        reasons.append("many_digits(-8)")

    # Decision
    if score >= 25:
        decision = "keep"
    elif score >= 0:
        decision = "review"
    else:
        decision = "exclude"

    if not reasons:
        reasons.append("no_strong_signal")
    return score, decision, reasons


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        has_header = "domain" in sample.splitlines()[0].lower() if sample else False

        if has_header:
            reader = csv.DictReader(f)
            return [dict(r) for r in reader]

        # Fichier 1 colonne sans header
        rows: list[dict[str, str]] = []
        for line in f:
            value = line.strip()
            if not value:
                continue
            rows.append({"domain": value})
        return rows


def write_csv(path: Path, rows: Iterable[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


OUTPUT_FIELDS = ["domain", "prefilter_score", "prefilter_reasons"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prefiltre offline de domaines (rule-based) avant crawl/scoring."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="CSV d'entree (avec colonne 'domain') ou fichier 1-colonne",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Dossier de sortie (defaut: ./data/<nom_fichier>_prefilter/)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = input_path.parent / f"{input_path.stem}_prefilter"

    rows = read_rows(input_path)
    if not rows:
        raise SystemExit(f"Aucune ligne lue dans {input_path}")

    keep_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    exclude_rows: list[dict[str, str]] = []

    for idx, row in enumerate(rows, start=1):
        raw_domain = row.get("domain", "") or row.get("url", "") or ""
        domain = normalize_domain(raw_domain)
        if not domain:
            continue

        score, decision, reasons = score_domain(domain, DEFAULT_RULES)
        entry = {
            "domain": domain,
            "prefilter_score": str(score),
            "prefilter_reasons": " | ".join(reasons),
        }

        if decision == "keep":
            keep_rows.append(entry)
        elif decision == "review":
            review_rows.append(entry)
        else:
            exclude_rows.append(entry)

    sort_key = lambda r: (-int(r["prefilter_score"]), r["domain"])
    keep_rows.sort(key=sort_key)
    review_rows.sort(key=sort_key)
    exclude_rows.sort(key=sort_key)

    out_keep = out_dir / "keep.csv"
    out_review = out_dir / "review.csv"
    out_exclude = out_dir / "exclude.csv"

    write_csv(out_keep, keep_rows, OUTPUT_FIELDS)
    write_csv(out_review, review_rows, OUTPUT_FIELDS)
    write_csv(out_exclude, exclude_rows, OUTPUT_FIELDS)

    total = len(keep_rows) + len(review_rows) + len(exclude_rows)
    print(f"[prefilter] total={total} keep={len(keep_rows)} review={len(review_rows)} exclude={len(exclude_rows)}")
    print(f"[prefilter] keep={out_keep}")
    print(f"[prefilter] review={out_review}")
    print(f"[prefilter] exclude={out_exclude}")


if __name__ == "__main__":
    main()

