"""Export liste Tranco sans crawl (_csv_rows_from_discovery_list_only)."""
from seed_builder_prospects.cli import _csv_rows_from_discovery_list_only
from seed_builder_prospects.providers.base import DiscoveryResult


def test_list_only_respects_max_and_dedup() -> None:
    dr = [
        DiscoveryResult(
            url="https://a.fr/",
            source_name="tranco",
            discovery_reason="Tranco #1",
        ),
        DiscoveryResult(
            url="https://b.fr/",
            source_name="tranco",
            discovery_reason="Tranco #2",
        ),
        DiscoveryResult(
            url="https://www.a.fr/",
            source_name="tranco",
            discovery_reason="dup",
        ),
    ]
    rows = _csv_rows_from_discovery_list_only(dr, max_rows=10)
    assert len(rows) == 2
    domains = {r["domain"] for r in rows}
    assert domains == {"a.fr", "b.fr"}
    assert rows[0]["country"] == "FR"
    assert "tranco_list_only" in rows[0]["evidence"]
