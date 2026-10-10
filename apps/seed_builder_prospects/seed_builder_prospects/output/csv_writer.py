"""
Export CSV : domain, brand_name, country, category, confidence_score, evidence, tags, associated_domains.
"""
import csv
from pathlib import Path
from typing import Any

def row_for_prospect(
    domain: str,
    brand_name: str,
    country: str,
    category: str,
    confidence_score: int,
    evidence: str,
    tags: list[str] | None = None,
    associated_domains: list[dict[str, Any]] | None = None,
    working_paths: list[str] | None = None,
    segment: str | None = None,
    segment_confidence: int | None = None,
    segment_reason: str | None = None,
) -> dict[str, Any]:
    """
    Crée une ligne CSV pour un prospect.
    tags: liste de tags (ex: ['agence_growth', 'agence_recrutement'])
    associated_domains: liste de dicts avec domain, tags, anchor_text
    """
    # Convertir les tags en string (séparés par des virgules)
    tags_str = ",".join(tags) if tags else ""
    
    # Convertir les domaines associés en string format: "domain1:tag1,tag2|domain2:tag3"
    if associated_domains:
        assoc_str = "|".join([
            f"{ad['domain']}:{','.join(ad.get('tags', []))}"
            for ad in associated_domains
        ])
    else:
        assoc_str = ""
    
    # working_paths : URLs internes qui ont bien répondu et servi à scorer le domaine
    working_paths_str = "|".join(working_paths) if working_paths else ""
    
    return {
        "domain": domain,
        "brand_name": brand_name,
        "country": country,
        "category": category,
        "confidence_score": confidence_score,
        "evidence": evidence,
        "tags": tags_str,
        "associated_domains": assoc_str,
        "working_paths": working_paths_str,
        "segment": segment or "",
        "segment_confidence": segment_confidence if segment_confidence is not None else "",
        "segment_reason": segment_reason or "",
    }


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """Écrit le CSV avec en-têtes standard."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "domain",
        "brand_name",
        "country",
        "category",
        "confidence_score",
        "evidence",
        "tags",
        "associated_domains",
        "working_paths",
        "segment",
        "segment_confidence",
        "segment_reason",
    ]
    if not rows:
        # Écrire quand même les en-têtes
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
