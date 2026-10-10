"""
Debug JSONL : pour chaque domaine, URLs fetch, status, signaux, score breakdown, exclusions.
"""
import json
from pathlib import Path
from typing import Any, Optional


def write_debug_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    """Une ligne JSON par enregistrement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def debug_record(
    domain: str,
    *,
    urls_fetched: Optional[list[dict[str, Any]]] = None,
    signals: Optional[dict[str, Any]] = None,
    score_breakdown: Optional[dict[str, Any]] = None,
    excluded: bool = False,
    exclusion_reason: Optional[str] = None,
    final_score: Optional[int] = None,
) -> dict[str, Any]:
    """Construit un enregistrement debug."""
    out: dict[str, Any] = {"domain": domain}
    if urls_fetched is not None:
        out["urls_fetched"] = urls_fetched
    if signals is not None:
        out["signals"] = signals
    if score_breakdown is not None:
        out["score_breakdown"] = score_breakdown
    if final_score is not None:
        out["score"] = final_score
    out["excluded"] = excluded
    if exclusion_reason:
        out["exclusion_reason"] = exclusion_reason
    return out
