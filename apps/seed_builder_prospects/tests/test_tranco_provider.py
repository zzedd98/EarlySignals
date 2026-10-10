"""Tests TrancoProvider (CSV local, sans réseau)."""
from pathlib import Path

from seed_builder_prospects.providers.tranco import TrancoProvider


def test_tranco_provider_filters_tld_and_limit(tmp_path: Path) -> None:
    csv_file = tmp_path / "mini.csv"
    csv_file.write_text(
        "1,google.com\n"
        "2,example.fr\n"
        "3,another.fr\n"
        "4,shop.example.fr\n",
        encoding="utf-8",
    )
    p = TrancoProvider(csv_file, tld_suffix=".fr")
    out = p.discover(queries=[], max_results=10, dedup_by_domain=True)
    domains = [r.url for r in out]
    assert len(domains) == 3
    assert all(".fr" in u or u.endswith(".fr") for u in domains)
    assert any("example.fr" in u for u in domains)


def test_tranco_provider_max_results(tmp_path: Path) -> None:
    csv_file = tmp_path / "mini.csv"
    csv_file.write_text(
        "1,a.fr\n2,b.fr\n3,c.fr\n",
        encoding="utf-8",
    )
    p = TrancoProvider(csv_file, tld_suffix="fr")
    out = p.discover(queries=[], max_results=2, dedup_by_domain=True)
    assert len(out) == 2
