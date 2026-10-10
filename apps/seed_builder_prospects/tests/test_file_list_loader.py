"""Chargement CSV seed (file_list)."""
from pathlib import Path

from seed_builder_prospects.providers.file_list import (
    FileListProvider,
    load_discovery_from_seed_csv,
)


def test_load_discovery_slice(tmp_path: Path) -> None:
    p = tmp_path / "s.csv"
    p.write_text(
        "domain,other\n"
        "aaa.fr,1\n"
        "bbb.fr,2\n"
        "ccc.fr,3\n"
        "ddd.fr,4\n",
        encoding="utf-8",
    )
    full = load_discovery_from_seed_csv(p)
    assert len(full) == 4
    mid = load_discovery_from_seed_csv(p, offset=1, limit=2)
    assert len(mid) == 2
    assert all("fr" in r.url for r in mid)


def test_load_grenouillemoi_format(tmp_path: Path) -> None:
    p = tmp_path / "grenouillemoi.csv"
    p.write_text(
        "Nom,Description,Type,Zone,Quartier,Ilot,URL,Twitter\n"
        'Foo,"Desc, with comma",Solution,Ventes,CC,CCaaS,https://viadialog.com/,@foo\n'
        'Bar,Other,Solution,RH,Paie,,https://nibelis.com/,\n'
        'Foo dup,Other,Solution,RH,Paie,,https://www.viadialog.com/foo,@foo\n',
        encoding="utf-8",
    )
    out = load_discovery_from_seed_csv(p, input_format="grenouillemoi")
    assert len(out) == 2
    domains = {r.url for r in out}
    assert any("viadialog.com" in u for u in domains)
    assert any("nibelis.com" in u for u in domains)
    assert all(r.discovery_reason == "grenouillemoi" for r in out)


def test_file_list_provider_dedup(tmp_path: Path) -> None:
    p = tmp_path / "t.txt"
    p.write_text("dup.fr\nwww.dup.fr\n", encoding="utf-8")
    prov = FileListProvider(p)
    out = prov.discover([], max_results=10, dedup_by_domain=True)
    assert len(out) == 1
