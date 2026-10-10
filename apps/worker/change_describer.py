"""Résumés courts et lisibles des changements détectés (FR)."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from app.models.signal import Signal

SIGNAL_LABELS = {
    "jobs": "Recrutement",
    "pricing_change": "Tarification",
    "tool_added": "Outil marketing/tech",
    "new_product": "Nouveau produit ou service",
    "partnership": "Partenariat",
    "expansion": "Expansion",
    "funding": "Financement",
    "new_site": "Nouveau site",
    "page_redesign": "Refonte de la page",
    "recent_activity": "Activité récente",
    "minor_activity": "Modification mineure",
}


def _truncate(text: str, max_len: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _url_path_label(url: str) -> str:
    path = urlparse(url or "").path.strip("/") or "/"
    return path


def _format_price_change(price_info: Optional[dict[str, Any]]) -> Optional[str]:
    if not price_info or not price_info.get("has_price_change"):
        return None
    old_prices = price_info.get("old_prices") or []
    new_prices = price_info.get("new_prices") or []
    if old_prices and new_prices:
        old_min = min(old_prices)
        new_min = min(new_prices)
        if old_min != new_min:
            return f"prix affichés {old_min:g}€ → {new_min:g}€"
    if new_prices and not old_prices:
        return f"nouveaux prix affichés (à partir de {min(new_prices):g}€)"
    if old_prices and not new_prices:
        return "suppression de montants tarifaires précédemment visibles"
    return "modification des montants tarifaires sur la page"


def _snippet_from_change(change_analysis: Optional[dict[str, Any]]) -> str:
    if not change_analysis:
        return ""
    added = (change_analysis.get("added_text") or "").strip()
    if added:
        return _truncate(added)
    removed = (change_analysis.get("removed_text") or "").strip()
    if removed:
        return f"Contenu retiré : {_truncate(removed, 100)}"
    return ""


def describe_signal_change(
    signal: Signal,
    change_analysis: Optional[dict[str, Any]] = None,
) -> str:
    """Construit un descriptif bref du changement pour logs et why_it_matters."""
    payload = signal.payload_json or {}
    signal_label = SIGNAL_LABELS.get(signal.type, signal.type)
    url = signal.proof_url or ""
    path = _url_path_label(url)
    snippet = _snippet_from_change(change_analysis)

    if signal.type == "jobs":
        keywords = payload.get("keywords_found") or []
        via = payload.get("detected_via")
        if keywords:
            kw_str = ", ".join(keywords[:5])
            extra = f" (+{len(keywords) - 5})" if len(keywords) > 5 else ""
            return (
                f"{signal_label} : nouveaux termes détectés ({kw_str}{extra}) "
                f"sur {path}"
            )
        if via == "url_change":
            return f"{signal_label} : nouvelle page ou section carrières ({path})"
        if snippet:
            return f"{signal_label} sur {path} — extrait ajouté : « {snippet} »"
        return f"{signal_label} : contenu recrutement ajouté ou mis à jour ({path})"

    if signal.type == "pricing_change":
        via = payload.get("detected_via")
        price_info = payload.get("price_change") or (
            (change_analysis or {}).get("price_change")
        )
        price_part = _format_price_change(price_info)
        if via == "url_change":
            base = f"{signal_label} : nouvelle page tarifs ({path})"
            return f"{base} ({price_part})" if price_part else base
        if via == "price_change" and price_part:
            return f"{signal_label} : {price_part} sur {path}"
        if snippet:
            return f"{signal_label} sur {path} — « {snippet} »"
        return f"{signal_label} : section prix ou forfaits modifiée ({path})"

    if signal.type == "tool_added":
        tool = payload.get("tool") or "outil inconnu"
        return f"{signal_label} : intégration de {tool} détectée sur {path}"

    if signal.type == "new_product":
        if snippet:
            return f"{signal_label} sur {path} — « {snippet} »"
        return f"{signal_label} : annonce ou page produit mise en avant ({path})"

    if signal.type in ("partnership", "expansion", "funding"):
        via = payload.get("detected_via")
        if via == "url":
            return f"{signal_label} : nouvelle page dédiée ({path})"
        if snippet:
            return f"{signal_label} sur {path} — « {snippet} »"
        return f"{signal_label} : nouveau contenu détecté ({path})"

    if signal.type == "page_redesign":
        similarity = payload.get("similarity")
        sim_part = f", similarité {similarity:.0%}" if similarity is not None else ""
        if snippet:
            return (
                f"{signal_label} sur {path}{sim_part} — contenu restructuré : « {snippet} »"
            )
        return (
            f"{signal_label} : restructuration importante du contenu ({path}{sim_part})"
        )

    if signal.type == "recent_activity":
        if snippet:
            return f"{signal_label} sur {path} — « {snippet} »"
        return f"{signal_label} : mise à jour du contenu sans signal métier explicite ({path})"

    if signal.type == "minor_activity":
        if snippet:
            return (
                f"{signal_label} sur {path}, signe d'activité — « {snippet} »"
            )
        return f"{signal_label} sur {path}, signe d'activité sur le site"

    if snippet:
        return f"{signal_label} ({path}) — « {snippet} »"
    return f"{signal_label} détecté sur {path}"
