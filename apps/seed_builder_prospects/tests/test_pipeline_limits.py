"""Tests des plafonds pipeline (--max-links / --max-results, 0 = illimité)."""

from seed_builder_prospects.cli import _merge_csv_rows_by_domain
from seed_builder_prospects.config import (
    UNLIMITED_MAX,
    format_pipeline_limit,
    is_unlimited,
    limit_reached,
)
from seed_builder_prospects.providers.file_list import FileListProvider


def test_unlimited_helpers():
    assert is_unlimited(UNLIMITED_MAX)
    assert is_unlimited(-1)
    assert not is_unlimited(10)
    assert not limit_reached(5, 0)
    assert not limit_reached(999, 0)
    assert limit_reached(10, 10)
    assert format_pipeline_limit(0) == "illimité"
    assert format_pipeline_limit(100) == "100"


def test_merge_csv_unlimited_keeps_all_rows():
    rows = [
        {"domain": "a.com", "confidence_score": "10"},
        {"domain": "b.com", "confidence_score": "20"},
        {"domain": "c.com", "confidence_score": "30"},
    ]
    merged = _merge_csv_rows_by_domain(rows, UNLIMITED_MAX)
    assert len(merged) == 3


def test_file_list_discover_unlimited(tmp_path):
    csv_path = tmp_path / "domains.csv"
    csv_path.write_text("domain\none.test\n two.test \n", encoding="utf-8")
    out = FileListProvider(csv_path).discover([], max_results=UNLIMITED_MAX)
    assert len(out) == 2
