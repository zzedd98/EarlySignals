"""Tests unitaires pour les résumés de changement."""

import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
API_APP_DIR = ROOT_DIR / "apps" / "api"
if str(API_APP_DIR) not in sys.path:
    sys.path.insert(0, str(API_APP_DIR))

from app.models.signal import Signal

from change_describer import describe_signal_change


def test_jobs_with_keywords():
    signal = Signal(
        domain_id=None,
        type="jobs",
        proof_url="https://careers.example.com/jobs",
        detected_at=datetime.utcnow(),
        payload_json={
            "keywords_found": ["hiring", "careers"],
            "detected_via": "new_content",
        },
    )
    summary = describe_signal_change(signal)
    assert "Recrutement" in summary
    assert "hiring" in summary


def test_tool_added():
    signal = Signal(
        domain_id=None,
        type="tool_added",
        proof_url="https://example.com/",
        detected_at=datetime.utcnow(),
        payload_json={"tool": "hubspot"},
    )
    summary = describe_signal_change(signal)
    assert "hubspot" in summary


def test_pricing_with_snippet():
    signal = Signal(
        domain_id=None,
        type="pricing_change",
        proof_url="https://example.com/pricing",
        detected_at=datetime.utcnow(),
        payload_json={"detected_via": "content"},
    )
    summary = describe_signal_change(
        signal,
        change_analysis={
            "added_text": "Nouveau forfait Pro à 99€ par mois pour les équipes.",
        },
    )
    assert "Tarification" in summary
    assert "forfait" in summary.lower() or "99" in summary
