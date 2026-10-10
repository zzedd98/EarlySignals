"""Niveaux d'importance des signaux (fort / moyen / faible)."""

from __future__ import annotations

from typing import Any, Literal, Optional

Importance = Literal["weak", "medium", "strong"]

IMPORTANCE_VALUES: tuple[Importance, ...] = ("weak", "medium", "strong")

IMPORTANCE_LABELS_FR: dict[str, str] = {
    "strong": "Fort",
    "medium": "Moyen",
    "weak": "Faible",
}

# Importance par défaut selon le type de signal métier.
SIGNAL_TYPE_IMPORTANCE: dict[str, Importance] = {
    "jobs": "strong",
    "pricing_change": "strong",
    "new_product": "strong",
    "expansion": "strong",
    "funding": "strong",
    "partnership": "strong",
    "tool_added": "medium",
    "new_site": "medium",
    "page_redesign": "medium",
    "recent_activity": "medium",
    "minor_activity": "weak",
}


def resolve_signal_importance(
    signal_type: str,
    payload: Optional[dict[str, Any]] = None,
) -> Importance:
    """
    Détermine l'importance d'un signal.
    Le payload peut surcharger (signaux fallback d'activité).
    """
    if payload:
        override = payload.get("importance")
        if override in IMPORTANCE_VALUES:
            return override  # type: ignore[return-value]

    return SIGNAL_TYPE_IMPORTANCE.get(signal_type, "strong")


def is_valid_importance(value: Optional[str]) -> bool:
    return value in IMPORTANCE_VALUES


# Icônes console worker (temps réel)
SIGNAL_LOG_ICONS: dict[str, str] = {
    "strong": "🟢",
    "medium": "🟠",
    "weak": "·",
}

IMPORTANCE_RANK: dict[str, int] = {
    "weak": 0,
    "medium": 1,
    "strong": 2,
}


def signal_log_icon(importance: str) -> str:
    return SIGNAL_LOG_ICONS.get(importance, SIGNAL_LOG_ICONS["strong"])


def format_signal_log_prefix(importance: str) -> str:
    """Préfixe lisible : '🟢 Signal [Fort]' / '🟠 Signal [Moyen]' / '· Signal [Faible]'."""
    icon = signal_log_icon(importance)
    label = IMPORTANCE_LABELS_FR.get(importance, importance)
    return f"{icon} Signal [{label}]"
