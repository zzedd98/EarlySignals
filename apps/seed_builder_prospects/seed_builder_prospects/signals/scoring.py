"""
Scoring 0..100 : bonus et pénalités à partir des preuves agrégées.
"""
from dataclasses import dataclass, field
from typing import Any

from seed_builder_prospects.config import SCORING_BONUS, SCORING_PENALTY


@dataclass
class ScoreBreakdown:
    """Détail du score pour debug."""
    raw_bonus: int = 0
    raw_penalty: int = 0
    details: dict[str, Any] = field(default_factory=dict)


def compute_score(
    *,
    sales_led_cta: bool = False,
    pricing: bool = False,
    recruitment: bool = False,
    clients_case_studies: bool = False,
    tools_count: int = 0,
    france_indices: bool = False,
    ecommerce: bool = False,
    agency_freelance: bool = False,
    directory_marketplace: bool = False,
    blocked_or_empty: bool = False,
    non_fr_no_indices: bool = False,
) -> tuple[int, ScoreBreakdown]:
    """
    Calcule le score 0..100 et le breakdown.
    """
    breakdown = ScoreBreakdown()
    bonus = 0
    penalty = 0

    if sales_led_cta:
        b = SCORING_BONUS.get("sales_led_cta", 30)
        bonus += b
        breakdown.details["sales_led_cta"] = b
    if pricing:
        b = SCORING_BONUS.get("pricing_plans", 20)
        bonus += b
        breakdown.details["pricing_plans"] = b
    if recruitment:
        b = SCORING_BONUS.get("recruitment", 25)
        bonus += b
        breakdown.details["recruitment"] = b
    if clients_case_studies:
        b = SCORING_BONUS.get("clients_case_studies", 15)
        bonus += b
        breakdown.details["clients_case_studies"] = b
    if tools_count > 0:
        b = SCORING_BONUS.get("tools_marketing_sales", 10)
        bonus += b
        breakdown.details["tools"] = b
    if france_indices:
        b = SCORING_BONUS.get("france_indices", 10)
        bonus += b
        breakdown.details["france_indices"] = b

    if ecommerce:
        p = SCORING_PENALTY.get("ecommerce", 40)
        penalty += p
        breakdown.details["penalty_ecommerce"] = p
    if directory_marketplace:
        p = SCORING_PENALTY.get("directory_marketplace", 60)
        penalty += p
        breakdown.details["penalty_directory"] = p
    if agency_freelance:
        p = SCORING_PENALTY.get("agency_freelance", 50)
        penalty += p
        breakdown.details["penalty_agency"] = p
    if blocked_or_empty:
        p = SCORING_PENALTY.get("blocked_or_empty", 30)
        penalty += p
        breakdown.details["penalty_blocked"] = p
    if non_fr_no_indices:
        p = SCORING_PENALTY.get("non_fr_no_indices", 25)
        penalty += p
        breakdown.details["penalty_non_fr"] = p

    breakdown.raw_bonus = bonus
    breakdown.raw_penalty = penalty
    score = max(0, min(100, bonus - penalty))
    return score, breakdown


def score_breakdown(breakdown: ScoreBreakdown) -> dict[str, Any]:
    """Retourne le breakdown sous forme dict pour JSON."""
    return {
        "raw_bonus": breakdown.raw_bonus,
        "raw_penalty": breakdown.raw_penalty,
        "details": breakdown.details,
    }
