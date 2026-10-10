"""
CLI Seed Builder Prospects : découverte -> validation -> scoring -> CSV + debug JSONL.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv
from tqdm import tqdm

# Charger les variables d'environnement depuis .env
load_dotenv()

from seed_builder_prospects.config import (
    QUERY_PACK_FR_PROSPECTS_GROWTH_B2B,
    QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_CLIENTS_CASE,
    QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_PRICING,
    QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_RECRUITMENT,
    QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_SALES_LED,
    QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_TEST,
    get_full_queries,
    MIN_SCORE_DEFAULT,
    MAX_PAGES_PER_DOMAIN,
    MIN_PAGES_PER_DOMAIN,
    UNLIMITED_MAX,
    is_unlimited,
    limit_reached,
    format_pipeline_limit,
)
from seed_builder_prospects.logging_utils import setup_logging, get_logger

# Valeur interne pour les jobs scoring sans proxy HTTP (connexion directe).
DIRECT_PROXY_SENTINEL = "__direct__"
from seed_builder_prospects.cache import get_cached_html, set_cached_html
from seed_builder_prospects.crawl.http_client import fetch_url
from seed_builder_prospects.crawl.url_normalize import (
    canonical_domain_from_url,
    normalize_url,
)
from seed_builder_prospects.crawl.extractor import (
    extract_links,
    extract_page_evidence,
    PageEvidence,
)
from seed_builder_prospects.crawl.link_graph import select_pages_to_fetch
from seed_builder_prospects.signals.scoring import (
    compute_score,
    score_breakdown,
    ScoreBreakdown,
)
from seed_builder_prospects.signals.filters import (
    is_blacklisted_domain,
    should_hard_exclude,
)
from seed_builder_prospects.providers.base import DiscoveryResult
from seed_builder_prospects.providers.file_list import (
    FileListProvider,
    INPUT_FORMATS,
    load_discovery_from_seed_csv,
)
from seed_builder_prospects.output.csv_writer import write_csv, row_for_prospect
from seed_builder_prospects.output.debug_writer import write_debug_jsonl, debug_record

logger = get_logger(__name__)

QUERY_PACKS = {
    "fr_prospects_growth_b2b": QUERY_PACK_FR_PROSPECTS_GROWTH_B2B,
    "fr_prospects_growth_b2b_sales_led": QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_SALES_LED,
    "fr_prospects_growth_b2b_pricing": QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_PRICING,
    "fr_prospects_growth_b2b_recruitment": QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_RECRUITMENT,
    "fr_prospects_growth_b2b_clients_case": QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_CLIENTS_CASE,
    "fr_prospects_growth_b2b_test": QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_TEST,
}

SOURCES_AVAILABLE = ("google", "tranco", "file_list")

# Fichier CSV par défaut (référencé aussi par --preset pour détecter un --out explicite)
DEFAULT_CSV_OUT = "./data/seed_prospects_fr.csv"
PRESET_TRANCO_FR_10K_OUT = "./data/tranco_fr_10k.csv"
PRESET_TRANCO_FR_10K_COUNT = 10_000


def _apply_cli_preset(args: argparse.Namespace) -> None:
    """Applique --preset (flux prêt à l’emploi, sans crawl HTTP)."""
    preset = getattr(args, "preset", None)
    if not preset:
        return
    if preset == "tranco-fr-10k":
        args.sources = "tranco"
        if not getattr(args, "tranco_tld", None):
            args.tranco_tld = ".fr"
        args.max_links = PRESET_TRANCO_FR_10K_COUNT
        args.max_results = PRESET_TRANCO_FR_10K_COUNT
        args.tranco_list_only = True
        if getattr(args, "out", None) == DEFAULT_CSV_OUT:
            args.out = PRESET_TRANCO_FR_10K_OUT
        return
    raise SystemExit(f"preset inconnu: {preset}")


def _csv_rows_from_discovery_list_only(
    discovery_results: list[DiscoveryResult],
    max_rows: int,
) -> list[dict[str, Any]]:
    """Export CSV sans crawl : domaines issus de la découverte (ex. Tranco .fr)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dr in discovery_results:
        if limit_reached(len(rows), max_rows):
            break
        domain = canonical_domain_from_url(dr.url)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        reason = (dr.discovery_reason or "tranco").strip()
        rows.append(
            row_for_prospect(
                domain=domain,
                brand_name=domain,
                country="FR",
                category="prospect_growth_b2b",
                confidence_score=0,
                evidence=f"tranco_list_only | {reason}",
                tags=["tranco_fr"],
                associated_domains=None,
                working_paths=None,
            )
        )
    return rows


def cache_dir_from_args(args: argparse.Namespace) -> Optional[Path]:
    if getattr(args, "no_http_cache", False):
        return None
    return Path(args.cache_dir) if getattr(args, "cache_dir", None) else None


def _proxy_server_from_args(args: argparse.Namespace) -> Optional[str]:
    """Construit l'URL proxy (Google Playwright ou crawl HTTP du scoring).

    Priorité:
    1) --proxy (URL complète)
    2) --proxy-port (port seul, hôte par défaut 127.0.0.1)
    3) GOOGLE_PROXY ou BING_PROXY (nom historique) dans l'environnement
    """
    explicit_proxy = getattr(args, "proxy", None)
    if explicit_proxy:
        return explicit_proxy

    proxy_port = getattr(args, "proxy_port", None)
    if proxy_port is not None:
        return f"http://127.0.0.1:{proxy_port}"

    return os.getenv("GOOGLE_PROXY") or os.getenv("BING_PROXY")


def _get_provider(args: argparse.Namespace, source_id: str):
    """Retourne le provider Google (Playwright), Tranco ou file_list."""
    from seed_builder_prospects.providers.google_playwright import (
        GooglePlaywrightProvider,
    )
    from seed_builder_prospects.providers.tranco import TrancoProvider

    if source_id == "file_list":
        path = getattr(args, "input_domains", None)
        if not path:
            raise SystemExit("--input-domains requis pour source file_list")
        return FileListProvider(
            input_path=path,
            input_format=getattr(args, "input_format", "auto"),
        )
    if source_id == "google":
        proxy = None
        proxy_str = _proxy_server_from_args(args)
        if proxy_str:
            proxy = {"server": proxy_str}
        # Récupérer la clé API depuis l'argument ou le .env
        capsolver_api_key = getattr(args, "capsolver_api_key", None) or os.getenv(
            "CAPSOLVER_API_KEY"
        )
        speed_mode = getattr(args, "speed", "fast")
        return GooglePlaywrightProvider(
            headless=getattr(args, "headless", False),
            delay_min=getattr(args, "delay_min", 8),
            delay_max=getattr(args, "delay_max", 20),
            timeout=float(getattr(args, "timeout", 30)),
            proxy=proxy,
            capsolver_api_key=capsolver_api_key,
            speed_mode=speed_mode,
            page_limit_per_run=getattr(args, "google_reset_every_pages", 0),
            resume_state_file=getattr(
                args,
                "google_resume_state_file",
                "./.cache/seed_builder_prospects/google_resume_state.json",
            ),
            force_start_offset=getattr(args, "google_start", None),
        )
    if source_id == "tranco":
        csv_arg = getattr(args, "tranco_csv", None)
        csv_path = Path(csv_arg) if csv_arg else None
        if csv_path is not None and not csv_path.is_file():
            raise SystemExit(f"--tranco-csv fichier introuvable: {csv_path}")
        return TrancoProvider(
            csv_path,
            cache_dir=cache_dir_from_args(args),
            subdomains=bool(getattr(args, "tranco_subdomains", False)),
            tld_suffix=getattr(args, "tranco_tld", None),
            refresh=bool(getattr(args, "tranco_refresh", False)),
        )
    raise SystemExit(f"Source inconnue: {source_id}")


def _run_discovery_single_source(
    source_id: str, args: argparse.Namespace, max_per_source: int
) -> list[DiscoveryResult]:
    """Exécute la découverte pour une source et retourne la liste de candidats."""
    provider = _get_provider(args, source_id)

    if source_id == "google":
        pack = QUERY_PACKS.get(args.query_pack)
        if not pack:
            return []
        queries = get_full_queries(pack)
        worker_map = getattr(args, "google_workers_map", None)
        if worker_map:
            return _run_google_orchestrated_workers(queries, args, max_per_source)
        return provider.discover(
            queries, max_results=max_per_source, dedup_by_domain=True
        )
    if source_id == "tranco":
        return provider.discover(
            queries=[], max_results=max_per_source, dedup_by_domain=True
        )
    if source_id == "file_list":
        path = getattr(args, "input_domains", None)
        if not path:
            raise SystemExit("--input-domains requis pour source file_list")
        return FileListProvider(
            input_path=path,
            input_format=getattr(args, "input_format", "auto"),
        ).discover(
            queries=["file_list"],
            max_results=max_per_source,
            dedup_by_domain=True,
        )
    return []


def _parse_workers_map(mapping: str, option_label: str) -> list[tuple[int, int]]:
    """Parse '101:0,102:200,103:400,104:600' (port proxy -> offset de départ)."""
    out: list[tuple[int, int]] = []
    for raw in mapping.split(","):
        item = raw.strip()
        if not item:
            continue
        if ":" not in item:
            raise SystemExit(
                f"Format invalide dans {option_label}: '{item}' (attendu port:start)"
            )
        port_s, start_s = item.split(":", 1)
        port = int(port_s.strip())
        start = int(start_s.strip())
        out.append((port, max(0, start)))
    if not out:
        raise SystemExit(f"{option_label} vide")
    return out


def _parse_ports_csv(raw_ports: str, option_label: str) -> list[int]:
    """Parse '101,102,103,104' en liste de ports."""
    out: list[int] = []
    for raw in raw_ports.split(","):
        item = raw.strip()
        if not item:
            continue
        out.append(int(item))
    if not out:
        raise SystemExit(f"{option_label} vide")
    return out


def _parse_worker_slice(raw: str) -> tuple[int, int]:
    """Parse '0:2500' -> (start, end)."""
    if ":" not in raw:
        raise SystemExit(f"--worker-slice invalide: {raw!r} (attendu start:end)")
    start_s, end_s = raw.split(":", 1)
    start = int(start_s.strip())
    end = int(end_s.strip())
    if start < 0 or end <= start:
        raise SystemExit(f"--worker-slice invalide: {raw!r}")
    return start, end


def _load_score_proxy_urls(args: argparse.Namespace) -> list[str]:
    proxies_file = getattr(args, "proxies_file", None)
    if not proxies_file:
        return []
    from seed_builder_prospects.proxy_config import load_proxies_from_file

    return load_proxies_from_file(proxies_file)


def _build_score_jobs(
    args: argparse.Namespace, n_total: int
) -> list[tuple[int, str, int, int]]:
    """Construit les jobs (worker_id, http_proxy_url, start, end)."""
    configured_parallel = int(getattr(args, "score_workers_parallel", 0))
    proxy_urls = _load_score_proxy_urls(args)

    if proxy_urls:
        requested = configured_parallel if configured_parallel > 0 else len(proxy_urls)
        workers_count = max(1, requested)
        slice_size = max(1, math.ceil(n_total / workers_count))
        jobs: list[tuple[int, str, int, int]] = []
        for worker_idx in range(workers_count):
            start = worker_idx * slice_size
            end = min(start + slice_size, n_total)
            if start >= n_total:
                break
            proxy = proxy_urls[worker_idx % len(proxy_urls)]
            jobs.append((worker_idx + 1, proxy, start, end))
        return jobs

    if getattr(args, "score_workers_ports", None):
        ports = _parse_ports_csv(args.score_workers_ports, "--score-workers-ports")
        requested = configured_parallel if configured_parallel > 0 else len(ports)
        workers_count = max(1, requested)
        slice_size = max(1, math.ceil(n_total / workers_count))
        jobs = []
        for worker_idx in range(workers_count):
            start = worker_idx * slice_size
            end = min(start + slice_size, n_total)
            if start >= n_total:
                break
            port = ports[worker_idx % len(ports)]
            jobs.append((worker_idx + 1, f"http://127.0.0.1:{port}", start, end))
        return jobs

    if getattr(args, "score_workers_map", None):
        mapping_sorted = sorted(
            _parse_workers_map(args.score_workers_map, "--score-workers-map"),
            key=lambda x: x[1],
        )
        jobs = []
        for wi, (port, start) in enumerate(mapping_sorted):
            if wi + 1 < len(mapping_sorted):
                end = mapping_sorted[wi + 1][1]
            else:
                end = n_total
            end = min(max(end, start), n_total)
            if start >= n_total:
                logger.warning(
                    "[ScoreOrchestrator] Worker #%d start=%d >= total=%d, ignoré",
                    wi + 1,
                    start,
                    n_total,
                )
                continue
            if end <= start:
                logger.warning(
                    "[ScoreOrchestrator] Worker #%d (port %d) plage vide [%d:%d), ignoré",
                    wi + 1,
                    port,
                    start,
                    end,
                )
                continue
            jobs.append((wi + 1, f"http://127.0.0.1:{port}", start, end))
        if configured_parallel > 0:
            jobs = jobs[:configured_parallel]
        return jobs

    if configured_parallel > 0:
        workers_count = configured_parallel
        slice_size = max(1, math.ceil(n_total / workers_count))
        jobs = []
        for worker_idx in range(workers_count):
            start = worker_idx * slice_size
            end = min(start + slice_size, n_total)
            if start >= n_total:
                break
            jobs.append((worker_idx + 1, DIRECT_PROXY_SENTINEL, start, end))
        return jobs

    raise SystemExit(
        "Scoring multi-worker: indiquez --proxies-file, --score-workers-ports, "
        "--score-workers-map, ou --score-workers-parallel N (connexion directe sans proxy)"
    )


def _resolve_worker_http_proxy(http_proxy: Optional[str]) -> Optional[str]:
    if http_proxy is None or http_proxy == DIRECT_PROXY_SENTINEL:
        return None
    return http_proxy


def _proxy_label(http_proxy: Optional[str]) -> str:
    if http_proxy is None or http_proxy == DIRECT_PROXY_SENTINEL:
        return "direct"
    if "@" in http_proxy:
        return http_proxy.split("@", 1)[1]
    return http_proxy


def _merge_score_worker_csv_outputs(
    worker_out_paths: list[Path], max_valid_results: int
) -> list[dict]:
    all_rows: list[dict] = []
    for path in worker_out_paths:
        if not path.is_file():
            logger.warning("[ScoreOrchestrator] Sortie worker absente: %s", path)
            continue
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            all_rows.extend(list(reader))
    return _merge_csv_rows_by_domain(all_rows, max_valid_results)


def _wait_for_worker_done_files(
    done_paths: list[Path], poll_seconds: float = 3.0
) -> None:
    logger.info("[ScoreOrchestrator] Attente de %d worker(s)...", len(done_paths))
    while True:
        missing = [p for p in done_paths if not p.is_file()]
        if not missing:
            logger.info("[ScoreOrchestrator] Tous les workers ont terminé.")
            return
        time.sleep(poll_seconds)


def _launch_score_worker_terminal(argv: list[str], cwd: Path, title: str) -> None:
    if os.name == "nt":
        # CREATE_NEW_CONSOLE : 1 fenêtre cmd par worker, sans les pièges de "start".
        cwd_s = str(cwd.resolve())
        cmdline = subprocess.list2cmdline(argv)
        inner = f'title {title} & {cmdline}'
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            ["cmd.exe", "/k", inner],
            cwd=cwd_s,
            creationflags=creationflags,
        )
        return
    subprocess.Popen(argv, cwd=str(cwd))


def _build_score_worker_cli_argv(
    args: argparse.Namespace,
    worker_id: int,
    http_proxy: str,
    start: int,
    end: int,
    worker_out: Path,
    worker_done: Path,
) -> list[str]:
    argv: list[str] = [
        sys.executable,
        "-m",
        "seed_builder_prospects.cli",
        "--score-worker-run",
        "--input-domains",
        str(args.input_domains),
        "--worker-slice",
        f"{start}:{end}",
        "--worker-out",
        str(worker_out),
        "--worker-done",
        str(worker_done),
        "--max-pages",
        str(getattr(args, "max_pages", 5)),
        "--max-links",
        str(getattr(args, "max_links", UNLIMITED_MAX)),
        "--max-results",
        str(getattr(args, "max_results", UNLIMITED_MAX)),
        "--min-score",
        str(getattr(args, "min_score", MIN_SCORE_DEFAULT)),
        "--rate-limit",
        str(getattr(args, "rate_limit", 60)),
        "--timeout",
        str(getattr(args, "timeout", 10.0)),
        "--http-retries",
        str(getattr(args, "http_retries", 3)),
        "--http-backoff",
        str(getattr(args, "http_backoff", 2.0)),
        "--segment-min-score-recruitment",
        str(getattr(args, "segment_min_score_recruitment", 30)),
        "--segment-min-score-b2b-seller",
        str(getattr(args, "segment_min_score_b2b_seller", 60)),
        "--segment-min-score-multinationale",
        str(getattr(args, "segment_min_score_multinationale", 50)),
        "--segment-target",
        str(getattr(args, "segment_target", "auto")),
        "--cache-dir",
        str(getattr(args, "cache_dir", "./.cache/seed_builder_prospects")),
    ]
    if http_proxy == DIRECT_PROXY_SENTINEL:
        argv.append("--no-proxy")
    else:
        argv.extend(["--proxy", http_proxy])
    input_fmt = getattr(args, "input_format", "auto")
    if input_fmt and input_fmt != "auto":
        argv.extend(["--input-format", str(input_fmt)])
    if getattr(args, "no_http_cache", False):
        argv.append("--no-http-cache")
    if getattr(args, "recruitment_only", False):
        argv.append("--recruitment-only")
    if getattr(args, "segment_loose", False):
        argv.append("--segment-loose")
    if getattr(args, "debug", False):
        argv.append("--debug")
    if getattr(args, "debug_jsonl", None):
        dbg = Path(args.debug_jsonl)
        worker_dbg = dbg.parent / f"{dbg.stem}_worker_{worker_id:02d}{dbg.suffix}"
        argv.extend(["--debug-jsonl", str(worker_dbg)])
    return argv


def _run_standalone_score_worker(args: argparse.Namespace) -> None:
    start, end = _parse_worker_slice(args.worker_slice)
    in_path = Path(args.input_domains)
    all_dr = load_discovery_from_seed_csv(
        in_path, input_format=getattr(args, "input_format", "auto")
    )
    chunk = all_dr[start:end]
    if getattr(args, "no_proxy", False):
        http_proxy = None
    else:
        http_proxy = _proxy_server_from_args(args)
        if not http_proxy:
            raise SystemExit(
                "--proxy requis en mode --score-worker-run (ou utilisez --no-proxy)"
            )

    cache_dir = cache_dir_from_args(args)
    rate_limit_delay = 60.0 / max(1, args.rate_limit)
    max_pages = getattr(args, "max_pages", 5)

    proxy_log = "direct" if http_proxy is None else _proxy_label(http_proxy)
    logger.info(
        "[ScoreWorker] slice=%d:%d (%d domaines) proxy=%s -> %s",
        start,
        end,
        len(chunk),
        proxy_log,
        args.worker_out,
    )

    result = _run_file_list_worker_end_to_end(
        worker_id=1,
        http_proxy=http_proxy,
        start_offset=start,
        discovery_slice=chunk,
        args=args,
        cache_dir=cache_dir,
        min_score=args.min_score,
        timeout=args.timeout,
        rate_limit_delay=rate_limit_delay,
        max_pages_per_domain=max_pages,
        max_domains_to_scrape=len(chunk),
        max_valid_results=len(chunk),
    )

    write_csv(args.worker_out, result.csv_rows)
    done_path = Path(args.worker_done)
    done_path.parent.mkdir(parents=True, exist_ok=True)
    done_path.write_text("ok\n", encoding="utf-8")
    logger.info(
        "[ScoreWorker] Terminé: kept=%d | processed=%d | excluded=%d",
        len(result.csv_rows),
        result.processed_count,
        result.excluded_count,
    )
    if getattr(args, "debug_jsonl", None):
        write_debug_jsonl(args.debug_jsonl, result.debug_records)


def _run_score_jobs_in_threads(
    score_jobs: list[tuple[int, str, int, int]],
    all_dr: list[DiscoveryResult],
    args: argparse.Namespace,
    cache_dir: Optional[Path],
    max_pages: int,
    rate_limit_delay: float,
) -> tuple[list[dict], list[dict], list[_GoogleWorkerPipelineResult]]:
    workers_count = len(score_jobs)
    score_rows: list[dict] = []
    score_debug: list[dict] = []
    score_reports: list[_GoogleWorkerPipelineResult] = []

    with ThreadPoolExecutor(max_workers=max(1, workers_count)) as pool:
        futures_map = {}
        for worker_id, http_proxy, start, end in score_jobs:
            chunk = all_dr[start:end]
            if not chunk:
                continue
            slice_len = len(chunk)
            fut = pool.submit(
                _run_file_list_worker_end_to_end,
                worker_id,
                http_proxy,
                start,
                chunk,
                args,
                cache_dir,
                args.min_score,
                args.timeout,
                rate_limit_delay,
                max_pages,
                slice_len,
                slice_len,
            )
            futures_map[fut] = (worker_id, http_proxy, start, slice_len)

        for fut in as_completed(futures_map):
            worker_id, http_proxy, start, slice_len = futures_map[fut]
            try:
                result = fut.result()
            except Exception as e:
                logger.warning(
                    "[ScoreOrchestrator] Worker #%d (proxy=%s,start=%d) erreur: %s",
                    worker_id,
                    _proxy_label(http_proxy),
                    start,
                    e,
                )
                continue
            score_reports.append(result)
            score_rows.extend(result.csv_rows)
            score_debug.extend(result.debug_records)
            logger.info(
                "[ScoreOrchestrator] Worker #%d fini (proxy=%s,start=%d): entrées=%d, kept=%d",
                worker_id,
                _proxy_label(http_proxy),
                start,
                result.discovered_count,
                len(result.csv_rows),
            )

    return score_rows, score_debug, score_reports


def _split_input_domains_for_ports(
    input_path: str | Path,
    ports: list[int],
    output_dir: str | Path,
) -> list[Path]:
    """Découpe un CSV/TXT en N fichiers (N = nombre de ports)."""
    source = Path(input_path)
    if not source.exists() or not source.is_file():
        raise SystemExit(f"Fichier input introuvable: {source}")

    lines = source.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise SystemExit(f"Fichier vide: {source}")

    # Si 1ère ligne ressemble à un header CSV 'domain', on la préserve.
    first = lines[0].strip().lower()
    has_header = "," in first and "domain" in first
    header = lines[0] if has_header else None
    rows = lines[1:] if has_header else lines

    chunk_size = max(1, math.ceil(len(rows) / len(ports)))
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for idx, port in enumerate(ports):
        start = idx * chunk_size
        end = start + chunk_size
        chunk_rows = rows[start:end]
        out_path = out_dir / f"{source.stem}_port_{port}.csv"
        if header:
            content = "\n".join([header, *chunk_rows]) + "\n"
        else:
            content = "\n".join(chunk_rows) + ("\n" if chunk_rows else "")
        out_path.write_text(content, encoding="utf-8")
        created.append(out_path)
    return created


def _run_google_worker(
    worker_id: int,
    proxy_port: int,
    start_offset: int,
    queries: list[str],
    args: argparse.Namespace,
    max_per_source: int,
) -> list[DiscoveryResult]:
    worker_args = argparse.Namespace(**vars(args))
    worker_args.sources = "google"
    worker_args.proxy = None
    worker_args.proxy_port = proxy_port
    worker_args.google_start = start_offset
    worker_args.google_resume_state_file = (
        f"./.cache/seed_builder_prospects/google_resume_state_worker_{proxy_port}.json"
    )
    provider = _get_provider(worker_args, "google")
    logger.info(
        "[GoogleOrchestrator] Worker #%d démarré (proxy_port=%d, start=%d)",
        worker_id,
        proxy_port,
        start_offset,
    )
    results = provider.discover(
        queries, max_results=max_per_source, dedup_by_domain=True
    )
    logger.info(
        "[GoogleOrchestrator] Worker #%d terminé: %d candidats",
        worker_id,
        len(results),
    )
    return results


@dataclass
class _GoogleWorkerPipelineResult:
    worker_id: int
    proxy_port: int
    start_offset: int
    discovered_count: int
    csv_rows: list[dict]
    debug_records: list[dict]
    processed_count: int = 0
    excluded_count: int = 0
    blocked_count: int = 0


def _merge_csv_rows_by_domain(rows: list[dict], max_rows: int) -> list[dict]:
    """Fusionne des lignes CSV en dédupliquant par domaine (meilleur score conservé)."""
    by_domain: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        domain = str(row.get("domain", "")).strip().lower()
        if not domain:
            continue
        score = int(row.get("confidence_score", 0) or 0)
        if domain not in by_domain:
            by_domain[domain] = row
            order.append(domain)
            continue
        existing_score = int(by_domain[domain].get("confidence_score", 0) or 0)
        if score > existing_score:
            by_domain[domain] = row
    merged: list[dict] = []
    for domain in order:
        merged.append(by_domain[domain])
        if limit_reached(len(merged), max_rows):
            break
    return merged


def _run_google_worker_end_to_end(
    worker_id: int,
    proxy_port: int,
    start_offset: int,
    queries: list[str],
    args: argparse.Namespace,
    max_discovery: int,
    cache_dir: Optional[Path],
    min_score: int,
    timeout: float,
    rate_limit_delay: float,
    max_pages_per_domain: int,
    max_domains_to_scrape: int,
    max_valid_results: int,
) -> _GoogleWorkerPipelineResult:
    discovered = _run_google_worker(
        worker_id=worker_id,
        proxy_port=proxy_port,
        start_offset=start_offset,
        queries=queries,
        args=args,
        max_per_source=max_discovery,
    )
    worker_debug_records: list[dict] = []
    csv_rows = _run_pipeline(
        discovery_results=discovered,
        cache_dir=cache_dir,
        min_score=min_score,
        timeout=timeout,
        rate_limit_delay=rate_limit_delay,
        http_retries=int(getattr(args, "http_retries", 3)),
        http_backoff=float(getattr(args, "http_backoff", 2.0)),
        max_pages_per_domain=max_pages_per_domain,
        max_domains_to_scrape=max_domains_to_scrape,
        max_valid_results=max_valid_results,
        debug_records=worker_debug_records,
        http_proxy=None,
        recruitment_only=bool(getattr(args, "recruitment_only", False)),
        segment_target=str(getattr(args, "segment_target", "auto")),
        segment_strict=not bool(getattr(args, "segment_loose", False)),
        segment_min_score_recruitment=int(
            getattr(args, "segment_min_score_recruitment", 30)
        ),
        segment_min_score_b2b_seller=int(
            getattr(args, "segment_min_score_b2b_seller", 60)
        ),
        segment_min_score_multinationale=int(
            getattr(args, "segment_min_score_multinationale", 50)
        ),
        log_prefix=f"W{worker_id}|P{proxy_port}",
    )
    processed_count = len(worker_debug_records)
    excluded_count = sum(1 for r in worker_debug_records if r.get("excluded"))
    blocked_count = sum(
        1
        for r in worker_debug_records
        if str(r.get("exclusion_reason", "")) == "blocked_or_empty"
    )
    return _GoogleWorkerPipelineResult(
        worker_id=worker_id,
        proxy_port=proxy_port,
        start_offset=start_offset,
        discovered_count=len(discovered),
        csv_rows=csv_rows,
        debug_records=worker_debug_records,
        processed_count=processed_count,
        excluded_count=excluded_count,
        blocked_count=blocked_count,
    )


def _run_file_list_worker_end_to_end(
    worker_id: int,
    http_proxy: Optional[str],
    start_offset: int,
    discovery_slice: list[DiscoveryResult],
    args: argparse.Namespace,
    cache_dir: Optional[Path],
    min_score: int,
    timeout: float,
    rate_limit_delay: float,
    max_pages_per_domain: int,
    max_domains_to_scrape: int,
    max_valid_results: int,
) -> _GoogleWorkerPipelineResult:
    """Scoring HTTP pour un bloc de domaines (proxy HTTP optionnel)."""
    worker_debug_records: list[dict] = []
    resolved_proxy = _resolve_worker_http_proxy(http_proxy)
    proxy_label = _proxy_label(http_proxy)
    logger.info(
        "[ScoreOrchestrator] Worker #%d proxy=%s slice_len=%d start_offset=%d",
        worker_id,
        proxy_label,
        len(discovery_slice),
        start_offset,
    )
    csv_rows = _run_pipeline(
        discovery_results=discovery_slice,
        cache_dir=cache_dir,
        min_score=min_score,
        timeout=timeout,
        rate_limit_delay=rate_limit_delay,
        http_retries=int(getattr(args, "http_retries", 3)),
        http_backoff=float(getattr(args, "http_backoff", 2.0)),
        max_pages_per_domain=max_pages_per_domain,
        max_domains_to_scrape=max_domains_to_scrape,
        max_valid_results=max_valid_results,
        debug_records=worker_debug_records,
        http_proxy=resolved_proxy,
        recruitment_only=bool(getattr(args, "recruitment_only", False)),
        segment_target=str(getattr(args, "segment_target", "auto")),
        segment_strict=not bool(getattr(args, "segment_loose", False)),
        segment_min_score_recruitment=int(
            getattr(args, "segment_min_score_recruitment", 30)
        ),
        segment_min_score_b2b_seller=int(
            getattr(args, "segment_min_score_b2b_seller", 60)
        ),
        segment_min_score_multinationale=int(
            getattr(args, "segment_min_score_multinationale", 50)
        ),
        log_prefix=f"W{worker_id}|{proxy_label}",
    )
    processed_count = len(worker_debug_records)
    excluded_count = sum(1 for r in worker_debug_records if r.get("excluded"))
    blocked_count = sum(
        1
        for r in worker_debug_records
        if str(r.get("exclusion_reason", "")) == "blocked_or_empty"
    )
    return _GoogleWorkerPipelineResult(
        worker_id=worker_id,
        proxy_port=0,
        start_offset=start_offset,
        discovered_count=len(discovery_slice),
        csv_rows=csv_rows,
        debug_records=worker_debug_records,
        processed_count=processed_count,
        excluded_count=excluded_count,
        blocked_count=blocked_count,
    )


def _run_google_orchestrated_workers(
    queries: list[str], args: argparse.Namespace, max_per_source: int
) -> list[DiscoveryResult]:
    mapping = _parse_workers_map(args.google_workers_map, "--google-workers-map")
    configured_parallel = int(getattr(args, "google_workers_parallel", 0))
    if configured_parallel <= 0:
        workers_count = len(mapping)
    else:
        workers_count = min(len(mapping), configured_parallel)
    logger.info(
        "[GoogleOrchestrator] %d worker(s) configuré(s), exécution parallèle max=%d",
        len(mapping),
        workers_count,
    )

    merged: list[DiscoveryResult] = []
    seen: set[str] = set()
    worker_stats: list[dict[str, int | str]] = []
    with ThreadPoolExecutor(max_workers=workers_count) as pool:
        futures_map = {}
        for idx, (port, start) in enumerate(mapping, start=1):
            fut = pool.submit(
                _run_google_worker,
                idx,
                port,
                start,
                queries,
                args,
                max_per_source,
            )
            futures_map[fut] = (idx, port, start)

        for fut in as_completed(futures_map):
            idx, port, start = futures_map[fut]
            try:
                results = fut.result()
            except Exception as e:
                logger.warning(
                    "[GoogleOrchestrator] Worker #%d (port=%d,start=%d) en erreur: %s",
                    idx,
                    port,
                    start,
                    e,
                )
                continue
            raw_count = len(results)
            unique_added = 0
            for r in results:
                domain = canonical_domain_from_url(r.url)
                if not domain or domain in seen:
                    continue
                seen.add(domain)
                merged.append(r)
                unique_added += 1
                if len(merged) >= max_per_source:
                    worker_stats.append(
                        {
                            "worker": idx,
                            "port": port,
                            "start": start,
                            "raw": raw_count,
                            "added": unique_added,
                        }
                    )
                    logger.info(
                        "[GoogleOrchestrator] Worker #%d terminé (port=%d,start=%d): bruts=%d, ajoutés=%d",
                        idx,
                        port,
                        start,
                        raw_count,
                        unique_added,
                    )
                    logger.info(
                        "[GoogleOrchestrator] RÉCAP FINAL: workers_ok=%d/%d | candidats_uniques=%d | limite=%d",
                        len(worker_stats),
                        len(mapping),
                        len(merged),
                        max_per_source,
                    )
                    return merged
            worker_stats.append(
                {
                    "worker": idx,
                    "port": port,
                    "start": start,
                    "raw": raw_count,
                    "added": unique_added,
                }
            )
            logger.info(
                "[GoogleOrchestrator] Worker #%d terminé (port=%d,start=%d): bruts=%d, ajoutés=%d",
                idx,
                port,
                start,
                raw_count,
                unique_added,
            )
            logger.info(
                "[GoogleOrchestrator] Progression fusion: %d domaine(s) unique(s) cumulé(s)",
                len(merged),
            )
    if worker_stats:
        workers_sorted = sorted(worker_stats, key=lambda x: int(x["added"]), reverse=True)
        top = workers_sorted[: min(3, len(workers_sorted))]
        top_str = ", ".join(
            f"W{int(w['worker'])}@{int(w['port'])}/start={int(w['start'])}: +{int(w['added'])}"
            for w in top
        )
        logger.info(
            "[GoogleOrchestrator] RÉCAP FINAL: workers_ok=%d/%d | candidats_uniques=%d | top=%s",
            len(worker_stats),
            len(mapping),
            len(merged),
            top_str or "n/a",
        )
    else:
        logger.warning(
            "[GoogleOrchestrator] RÉCAP FINAL: aucun worker n'a produit de résultats"
        )
    return merged


def _merge_and_dedupe(
    results_per_source: list[tuple[str, list[DiscoveryResult]]], max_total: int
) -> list[DiscoveryResult]:
    """Fusionne les résultats de toutes les sources et déduplique par domaine (premier gagnant)."""
    seen: set[str] = set()
    merged: list[DiscoveryResult] = []
    for source_id, results in results_per_source:
        for r in results:
            domain = canonical_domain_from_url(r.url)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            merged.append(r)
            if limit_reached(len(merged), max_total):
                return merged
    return merged


def _aggregate_evidence(
    evidences: list[PageEvidence],
) -> tuple[dict[str, Any], str, str]:
    """Agrège les preuves de plusieurs pages. Retourne (signals_dict, evidence_string, brand_name)."""
    sales_led = any(e.sales_led_cta for e in evidences)
    pricing = any(e.pricing for e in evidences)
    recruitment = any(e.recruitment for e in evidences)
    clients = any(e.clients_case_studies for e in evidences)
    france = any(e.france_indices for e in evidences)
    agency = any(e.agency_freelance for e in evidences)
    ecommerce = any(e.ecommerce for e in evidences)
    all_tools: list[str] = []
    for e in evidences:
        all_tools.extend(e.tools)
    tools_list = list(dict.fromkeys(all_tools))

    # Brand: og:site_name > title (home) > h1 > domain
    brand = ""
    for e in evidences:
        if e.og_site_name:
            brand = e.og_site_name
            break
    if not brand and evidences:
        brand = (evidences[0].title or "").strip()
        if "|" in brand:
            brand = brand.split("|")[0].strip()
        if "-" in brand:
            brand = brand.split("-")[0].strip()
    if not brand and evidences and evidences[0].h1:
        brand = evidences[0].h1[0][:80]
    # Fallback domain will be set by caller

    # Evidence string compact
    parts = []
    if sales_led:
        parts.append("demo")
    if pricing:
        parts.append("pricing")
    if recruitment:
        parts.append("recrutement")
    if clients:
        parts.append("clients/case-studies")
    parts_str = "+".join(parts) if parts else "—"
    tools_str = "+".join(tools_list) if tools_list else "—"
    fr_str = "SIRET/FR trouvé" if france else "—"
    pages_str = ", ".join(e.url.split("/")[-1] or "/" for e in evidences[:5])
    titres = " | ".join(e.title[:60] for e in evidences if e.title)[:200]
    evidence_str = f"Signaux: {parts_str}; Outils: {tools_str}; FR: {fr_str}; Pages: {pages_str}; Titres: {titres}"

    signals_dict = {
        "sales_led_cta": sales_led,
        "pricing": pricing,
        "recruitment": recruitment,
        "clients_case_studies": clients,
        "france_indices": france,
        "agency_freelance": agency,
        "ecommerce": ecommerce,
        "tools": tools_list,
    }
    return signals_dict, evidence_str, brand


def _classify_segment(
    *,
    domain: str,
    evidences: list[PageEvidence],
    signals_dict: dict[str, Any],
    combined_text: str,
) -> tuple[str, int, str]:
    """
    Classe un domaine en segment métier:
    - multinationale
    - recruitment
    - b2b_seller
    - rejected (aucun segment fiable)
    """
    text = (combined_text or "").lower()
    urls = " ".join((e.url or "").lower() for e in evidences)
    titles = " ".join((e.title or "").lower() for e in evidences)

    has_recruitment = bool(signals_dict.get("recruitment"))
    has_sales = bool(signals_dict.get("sales_led_cta"))
    has_pricing = bool(signals_dict.get("pricing"))
    has_clients = bool(signals_dict.get("clients_case_studies"))

    # Indices "multinationale"
    corp_tokens = (
        "investor",
        "investisseurs",
        "governance",
        "annual report",
        "rapport annuel",
        "global",
        "worldwide",
        "countries",
        "our locations",
        "locations",
        "press release",
    )
    country_tokens = (
        "/fr/",
        "/en/",
        "/de/",
        "/es/",
        "/it/",
        "/pt/",
        "/nl/",
        "/jp/",
    )
    corp_hits = sum(1 for tok in corp_tokens if tok in text)
    country_hits = sum(1 for tok in country_tokens if tok in urls)
    has_investor_url = any("investor" in (e.url or "").lower() for e in evidences)
    has_press_url = any("press" in (e.url or "").lower() for e in evidences)
    multinational_score = min(
        100, corp_hits * 12 + country_hits * 8 + (20 if has_investor_url else 0) + (10 if has_press_url else 0)
    )
    multinational_must_have = (
        (corp_hits >= 2 and country_hits >= 1) or has_investor_url or ("global" in text and "countries" in text)
    )

    # Indices "recruitment"
    recruitment_tokens = (
        "careers",
        "career",
        "join us",
        "hiring",
        "we are hiring",
        "job openings",
        "offres d'emploi",
        "rejoignez-nous",
        "recrutement",
        "postuler",
    )
    recruitment_hits = sum(1 for tok in recruitment_tokens if tok in text)
    has_career_url = any(
        k in (e.url or "").lower()
        for e in evidences
        for k in ("career", "careers", "jobs", "job", "recrutement", "offres-emploi")
    )
    recruitment_score = min(
        100, (40 if has_recruitment else 0) + recruitment_hits * 8 + (20 if has_career_url else 0)
    )
    recruitment_must_have = has_career_url or (has_recruitment and recruitment_hits >= 2)

    # Indices "b2b_seller" (SaaS, prestations, produits/services pro)
    b2b_tokens = (
        "request a demo",
        "book a demo",
        "contact sales",
        "enterprise",
        "for business",
        "for companies",
        "b2b",
        "solutions",
        "plateforme",
        "logiciel",
        "saas",
        "entreprise",
        "entreprises",
        "professionnel",
        "professionnels",
        "prestataire",
        "prestation",
        "prestations",
        "nos services",
        "nos prestations",
        "pour les entreprises",
        "séminaire",
        "seminaire",
        "collaborateurs",
        "team building",
        "produit digital",
        "produits digitaux",
    )
    b2b_hits = sum(1 for tok in b2b_tokens if tok in text or tok in titles)
    b2b_score = min(
        100,
        (30 if has_sales else 0)
        + (25 if has_pricing else 0)
        + (15 if has_clients else 0)
        + b2b_hits * 4,
    )
    b2b_must_have = (
        has_sales
        or has_pricing
        or has_clients
        or b2b_hits >= 2
    )

    candidates: list[tuple[str, int, str]] = []
    if multinational_must_have:
        candidates.append(
            ("multinationale", multinational_score, f"corp_hits={corp_hits};country_hits={country_hits}")
        )
    if recruitment_must_have:
        candidates.append(
            ("recruitment", recruitment_score, f"recruitment_signal={int(has_recruitment)};career_url={int(has_career_url)}")
        )
    if b2b_must_have:
        candidates.append(
            ("b2b_seller", b2b_score, f"sales={int(has_sales)};pricing={int(has_pricing)};clients={int(has_clients)}")
        )

    if not candidates:
        if has_sales or has_pricing or has_clients or b2b_hits >= 1:
            return (
                "b2b_seller",
                max(b2b_score, 25),
                (
                    f"fallback_b2b_signals:sales={int(has_sales)};"
                    f"pricing={int(has_pricing)};clients={int(has_clients)};"
                    f"b2b_hits={b2b_hits}"
                ),
            )
        return "rejected", 0, "no_segment_match"
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0]


def _run_pipeline(
    discovery_results: list[Any],
    cache_dir: Optional[Path],
    min_score: int,
    timeout: float,
    rate_limit_delay: float,
    http_retries: int,
    http_backoff: float,
    max_pages_per_domain: int,
    max_domains_to_scrape: int,
    max_valid_results: int,
    debug_records: list[dict],
    http_proxy: Optional[str] = None,
    recruitment_only: bool = False,
    segment_target: str = "auto",
    segment_strict: bool = True,
    segment_min_score_recruitment: int = 30,
    segment_min_score_b2b_seller: int = 60,
    segment_min_score_multinationale: int = 50,
    log_prefix: str = "",
) -> list[dict]:
    """Pour chaque résultat de découverte : fetch home -> liens -> pages -> score -> filtre.

    Désormais, les domaines externes détectés sont également ajoutés à la file
    de traitement et passent par le même pipeline que les domaines initiaux.
    """
    csv_rows: list[dict] = []
    seen_domains: set[str] = set()
    min_pages = min(2, max_pages_per_domain)
    total_domains_processed = 0  # Compteur global de domaines analysés
    total_valid_results = 0  # Compteur de domaines valides gardés
    discovered_domains_total = len(discovery_results)
    # Le "max" affiché dans les logs doit refléter le volume réellement découvert
    # (borné par les limites de pipeline).
    domains_log_max = (
        discovered_domains_total
        if is_unlimited(max_domains_to_scrape)
        else min(max_domains_to_scrape, discovered_domains_total)
    )
    valid_log_max = (
        discovered_domains_total
        if is_unlimited(max_valid_results)
        else min(max_valid_results, discovered_domains_total)
    )

    # File de domaines à traiter (on pourra y ajouter les domaines externes)
    domains_queue: deque[Any] = deque(discovery_results)
    pbar = tqdm(desc="Domaines")

    pfx = f"[{log_prefix}] " if log_prefix else ""

    while domains_queue:
        dr = domains_queue.popleft()
        pbar.update(1)
        # Vérifier si on a atteint le max de domaines valides (arrêt immédiat)
        if limit_reached(total_valid_results, max_valid_results):
            logger.info(
                "Limite de résultats valides atteinte (%d/%s), arrêt du crawling",
                total_valid_results,
                format_pipeline_limit(max_valid_results),
            )
            break

        # Vérifier si on a atteint le max de domaines à scraper
        if limit_reached(total_domains_processed, max_domains_to_scrape):
            logger.info(
                "Limite de domaines à scraper atteinte (%d/%s), arrêt du crawling",
                total_domains_processed,
                format_pipeline_limit(max_domains_to_scrape),
            )
            break

        url = (
            dr.url
            if isinstance(dr, DiscoveryResult)
            else (dr if isinstance(dr, str) else getattr(dr, "url", ""))
        )
        source_name = (
            getattr(dr, "source_name", "") if isinstance(dr, DiscoveryResult) else ""
        )
        discovery_reason = (
            getattr(dr, "discovery_reason", "")
            if isinstance(dr, DiscoveryResult)
            else ""
        )
        domain = canonical_domain_from_url(url)
        if not domain or domain in seen_domains:
            continue
        if is_blacklisted_domain(domain):
            rec = debug_record(domain, excluded=True, exclusion_reason="blacklist")
            if source_name:
                rec["source_name"] = source_name
            if discovery_reason:
                rec["discovery_reason"] = discovery_reason
            debug_records.append(rec)
            logger.debug("[%s] blacklist, ignoré", domain)
            continue
        seen_domains.add(domain)

        logger.info(
            "%s[%s] crawl (source=%s) | Domaines scrappés: %d/%d | Résultats valides: %d/%d",
            pfx,
            domain,
            source_name or "?",
            total_domains_processed,
            domains_log_max,
            total_valid_results,
            valid_log_max,
        )
        logger.debug("  URL découverte: %s", url)

        # Toujours aller sur la homepage du domaine, pas sur l'URL découverte
        # Construire la vraie homepage à partir du domaine
        from urllib.parse import urlparse

        # Vérifier si l'URL originale contient /fr dans le chemin pour préserver ce préfixe
        parsed_url = urlparse(url if url.startswith("http") else f"https://{url}")
        if parsed_url.path and parsed_url.path.lower().startswith("/fr"):
            # L'URL découverte contient /fr, on garde ce préfixe pour la homepage
            home_url = f"https://{domain}/fr/"
        else:
            home_url = f"https://{domain}/"
        logger.debug(
            "  Homepage construite: %s (à partir du domaine: %s, URL originale: %s)",
            home_url,
            domain,
            url[:60],
        )
        cached = get_cached_html(cache_dir, home_url) if cache_dir else None
        if cached:
            home_html, home_status, redirect_chain = cached
            logger.info("%shome %s (cache) status=%s", pfx, home_url[:50], home_status)
        else:
            time.sleep(rate_limit_delay)
            home_status, home_html, redirect_chain = fetch_url(
                home_url,
                timeout=timeout,
                retries=http_retries,
                backoff=http_backoff,
                proxy=http_proxy,
            )
            if cache_dir:
                set_cached_html(
                    cache_dir, home_url, home_html, home_status, redirect_chain
                )
            logger.info("%shome %s status=%s", pfx, home_url[:50], home_status)
        final_url = redirect_chain[-1] if redirect_chain else home_url
        domain = canonical_domain_from_url(final_url)
        if not domain:
            continue

        if home_status >= 400 or not home_html.strip():
            rec = debug_record(
                domain,
                excluded=True,
                exclusion_reason="blocked_or_empty",
                final_score=0,
            )
            if source_name:
                rec["source_name"] = source_name
            if discovery_reason:
                rec["discovery_reason"] = discovery_reason
            debug_records.append(rec)
            logger.info("%s-> excluded: blocked_or_empty (status=%s)", pfx, home_status)
            total_domains_processed += 1  # Compter les domaines exclus
            continue

        # Internal links -> select pages
        links = extract_links(home_html, final_url)
        logger.debug("  %d lien(s) interne(s) trouvé(s) sur la homepage", len(links))

        # Utiliser max_pages_per_domain directement (pas de limite globale de liens)
        to_fetch = select_pages_to_fetch(
            links, final_url, max_pages=max_pages_per_domain, min_pages=min_pages
        )
        logger.debug("  %d page(s) sélectionnée(s) pour le crawling", len(to_fetch))

        evidences: list[PageEvidence] = []
        urls_fetched_debug: list[dict] = [
            {"url": home_url, "status": home_status, "redirect_chain": redirect_chain}
        ]

        ev0 = extract_page_evidence(home_url, home_html, home_status, redirect_chain)
        evidences.append(ev0)
        logger.debug("  [1/%d] Homepage analysée: %s", max_pages_per_domain, home_url)

        for idx, page_url in enumerate(to_fetch, start=2):
            if page_url == home_url or page_url == final_url:
                continue
            if len(evidences) >= max_pages_per_domain:
                break
            cached_p = get_cached_html(cache_dir, page_url) if cache_dir else None
            if cached_p:
                p_html, p_status, p_chain = cached_p
                logger.debug(
                    "  [%d/%d] %s (cache) status=%s",
                    idx,
                    max_pages_per_domain,
                    page_url[:60],
                    p_status,
                )
            else:
                time.sleep(rate_limit_delay)
                p_status, p_html, p_chain = fetch_url(
                    page_url,
                    timeout=timeout,
                    retries=http_retries,
                    backoff=http_backoff,
                    proxy=http_proxy,
                )
                if cache_dir:
                    set_cached_html(cache_dir, page_url, p_html, p_status, p_chain)
                logger.debug(
                    "  [%d/%d] %s status=%s",
                    idx,
                    max_pages_per_domain,
                    page_url[:60],
                    p_status,
                )
            urls_fetched_debug.append({"url": page_url, "status": p_status})
            if p_status == 200 and p_html:
                evidences.append(
                    extract_page_evidence(page_url, p_html, p_status, p_chain)
                )

        logger.info("%s%d page(s) récupérée(s) et analysée(s)", pfx, len(evidences))

        # Désactivation temporaire de la découverte de domaines externes :
        # on se limite aux pages internes / sous-domaines du domaine courant.
        signals_dict, evidence_str, brand = _aggregate_evidence(evidences)
        combined_text = " ".join(e.body_text for e in evidences)

        segment, segment_confidence, segment_reason = _classify_segment(
            domain=domain,
            evidences=evidences,
            signals_dict=signals_dict,
            combined_text=combined_text,
        )

        # Générer les tags pour le domaine principal basé sur les signaux détectés
        main_domain_tags: list[str] = []
        if recruitment_only:
            if signals_dict["recruitment"] and segment in ("recruitment", "multinationale", "b2b_seller"):
                main_domain_tags.append("agence_recrutement")
        else:
            if segment == "recruitment":
                main_domain_tags.append("agence_recrutement")
            elif segment == "b2b_seller":
                main_domain_tags.append("b2b_seller")
            elif segment == "multinationale":
                main_domain_tags.append("multinationale")
            else:
                if (
                    signals_dict["sales_led_cta"]
                    or signals_dict["pricing"]
                    or signals_dict["recruitment"]
                ):
                    main_domain_tags.append("agence_growth")
        if any(
            "saas" in t.lower() or "software" in t.lower() or "logiciel" in t.lower()
            for e in evidences
            for t in [e.title or "", e.h1[0] if e.h1 else ""]
        ):
            main_domain_tags.append("saas_b2b")
        if not main_domain_tags and segment != "rejected":
            main_domain_tags.append("domaine_principal")
        # On ne filtre plus les agences/marketplace - seulement les vrais problèmes de scraping
        excluded_hard, reason = should_hard_exclude(
            combined_text.lower(), exclude_agency=False
        )
        directory_marketplace = is_blacklisted_domain(domain)  # déjà filtré avant

        score, breakdown = compute_score(
            sales_led_cta=signals_dict["sales_led_cta"],
            pricing=signals_dict["pricing"],
            recruitment=signals_dict["recruitment"],
            clients_case_studies=signals_dict["clients_case_studies"],
            tools_count=len(signals_dict["tools"]),
            france_indices=signals_dict["france_indices"],
            ecommerce=False,  # Ne plus pénaliser l'ecommerce (on veut max de données)
            agency_freelance=False,  # Ne plus pénaliser les agences
            directory_marketplace=False,  # Ne plus pénaliser les marketplace
            blocked_or_empty=False,
            non_fr_no_indices=False,  # Ne plus pénaliser les sites non-FR (on veut max de données)
        )

        if segment == "rejected" and score > 0:
            segment = "b2b_seller"
            segment_confidence = max(segment_confidence, score)
            segment_reason = f"fallback_score_b2b(score={score});was={segment_reason}"
            if not recruitment_only:
                main_domain_tags = [
                    t for t in main_domain_tags if t not in ("agence_growth",)
                ]
                if "b2b_seller" not in main_domain_tags:
                    main_domain_tags.append("b2b_seller")

        # Mode strict recrutement: ignorer totalement min_score.
        # On garde uniquement les domaines avec signal recrutement
        # (et on conserve les exclusions "hard" techniques).
        segment_min_score_map = {
            "recruitment": segment_min_score_recruitment,
            "b2b_seller": segment_min_score_b2b_seller,
            "multinationale": segment_min_score_multinationale,
        }
        segment_min_score = segment_min_score_map.get(segment, min_score)

        if recruitment_only:
            excluded = excluded_hard or (segment != "recruitment")
        else:
            segment_mismatch = segment_target != "auto" and segment != segment_target
            segment_rejected = segment_strict and segment == "rejected"
            excluded = (
                excluded_hard
                or segment_mismatch
                or segment_rejected
                or score < segment_min_score
            )
        rec = debug_record(
            domain,
            urls_fetched=urls_fetched_debug,
            signals=signals_dict,
            score_breakdown=score_breakdown(breakdown),
            excluded=excluded,
            exclusion_reason=(
                reason
                if excluded_hard
                else (
                    "no_recruitment_signal"
                    if recruitment_only and segment != "recruitment"
                    else (
                        "segment_mismatch"
                        if (segment_target != "auto" and segment != segment_target)
                        else (
                            "segment_rejected"
                            if (segment_strict and segment == "rejected")
                            else (
                                "score < segment_min_score"
                                if score < segment_min_score
                                else None
                            )
                        )
                    )
                )
            ),
            final_score=score,
        )
        rec["segment"] = segment
        rec["segment_confidence"] = segment_confidence
        rec["segment_reason"] = segment_reason
        if source_name:
            rec["source_name"] = source_name
        if discovery_reason:
            rec["discovery_reason"] = discovery_reason
        debug_records.append(rec)

        # Logs détaillés avec explications
        if excluded:
            exclusion_reason = rec.get("exclusion_reason") or "score < min_score"
            if excluded_hard:
                logger.info("%s❌ EXCLU: %s (raison: %s)", pfx, domain, exclusion_reason)
                logger.info(
                    "%s→ Site non scrappable (antibot, bloqué, ou page vide)",
                    pfx,
                )
            elif exclusion_reason == "segment_rejected":
                logger.info(
                    "%s❌ EXCLU: %s (segment=%s, score=%d) — aucun segment métier reconnu",
                    pfx,
                    domain,
                    segment,
                    score,
                )
                logger.info(
                    "%s→ segment_reason=%s (utilisez --segment-loose pour garder quand même)",
                    pfx,
                    segment_reason,
                )
            elif exclusion_reason == "segment_mismatch":
                logger.info(
                    "%s❌ EXCLU: %s (segment=%s, cible=%s, score=%d)",
                    pfx,
                    domain,
                    segment,
                    segment_target,
                    score,
                )
            elif exclusion_reason == "score < segment_min_score":
                logger.info(
                    "%s❌ EXCLU: %s (score=%d < segment_min_score=%d, segment=%s)",
                    pfx,
                    domain,
                    score,
                    segment_min_score,
                    segment,
                )
                logger.info(
                    "%s→ Score insuffisant: bonus=%d, pénalités=%d",
                    pfx,
                    breakdown.raw_bonus,
                    breakdown.raw_penalty,
                )
            else:
                logger.info(
                    "%s❌ EXCLU: %s (raison=%s, score=%d, segment=%s)",
                    pfx,
                    domain,
                    exclusion_reason,
                    score,
                    segment,
                )
                if breakdown.details:
                    bonuses = {
                        k: v
                        for k, v in breakdown.details.items()
                        if not k.startswith("penalty_")
                    }
                    penalties = {
                        k: v
                        for k, v in breakdown.details.items()
                        if k.startswith("penalty_")
                    }
                    if bonuses:
                        logger.info(
                            "%s→ Bonus: %s",
                            pfx,
                            ", ".join(f"{k}={v}" for k, v in bonuses.items()),
                        )
                    if penalties:
                        logger.info(
                            "%s→ Pénalités: %s",
                            pfx,
                            ", ".join(f"{k}={v}" for k, v in penalties.items()),
                        )
        else:
            logger.info("%s✅ GARDÉ: %s (score=%d)", pfx, domain, score)
            logger.info(
                "%s→ Ajouté à la seed (score >= segment_min_score=%d)",
                pfx,
                segment_min_score,
            )
            if breakdown.details:
                bonuses = {
                    k: v
                    for k, v in breakdown.details.items()
                    if not k.startswith("penalty_")
                }
                if bonuses:
                    logger.info(
                        "%s→ Signaux détectés: %s",
                        pfx,
                        ", ".join(f"{k}={v}" for k, v in bonuses.items()),
                    )

        if excluded:
            total_domains_processed += 1  # Compter même les exclus
            continue

        # Construire la liste des pages qui ont bien répondu pour ce domaine
        working_paths = sorted(
            {e.url for e in evidences if e.url and e.status_code == 200}
        )

        # Ajouter le domaine valide au CSV (chaque domaine est indépendant)
        brand_name = brand or domain
        csv_rows.append(
            row_for_prospect(
                domain=domain,
                brand_name=brand_name,
                country="FR",
                category="prospect_growth_b2b",
                confidence_score=score,
                evidence=evidence_str,
                tags=main_domain_tags,
                associated_domains=[],
                working_paths=working_paths,
                segment=segment,
                segment_confidence=segment_confidence,
                segment_reason=segment_reason,
            )
        )
        total_domains_processed += 1  # Compter les domaines analysés
        total_valid_results += 1  # Compter les résultats valides

        # Vérifier si on a atteint le max de résultats valides (arrêt immédiat)
        if limit_reached(total_valid_results, max_valid_results):
            logger.info(
                "Limite de résultats valides atteinte (%d/%s), arrêt du crawling",
                total_valid_results,
                format_pipeline_limit(max_valid_results),
            )
            break

    pbar.close()
    return csv_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Builder Prospects - Early Signals"
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Sources (virgule): google, tranco, file_list. Ex: tranco,google",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="[Rétrocompat] Une seule source: google, tranco ou file_list. Ignoré si --sources est fourni.",
    )
    parser.add_argument(
        "--query-pack",
        default="fr_prospects_growth_b2b",
        help="Pack de requêtes (source google)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=UNLIMITED_MAX,
        help=(
            "Nombre max de domaines valides à garder dans le CSV "
            f"(défaut: {UNLIMITED_MAX} = illimité, tous les domaines valides)"
        ),
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=UNLIMITED_MAX,
        help=(
            "Nombre max de domaines à scraper au total "
            f"(défaut: {UNLIMITED_MAX} = illimité, tout le fichier / la découverte)"
        ),
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=MIN_SCORE_DEFAULT,
        help=f"Score minimum requis pour garder un domaine dans le CSV (défaut: {MIN_SCORE_DEFAULT}, 0-100)",
    )
    parser.add_argument("--out", default=DEFAULT_CSV_OUT)
    parser.add_argument("--cache-dir", default="./.cache/seed_builder_prospects")
    parser.add_argument(
        "--no-http-cache",
        action="store_true",
        help="Désactive le cache HTML (refetch systématique via proxy). Utile pour relancer un scoring.",
    )
    parser.add_argument("--debug-jsonl", default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--input-domains",
        default=None,
        help="CSV (colonne domain) ou TXT : source file_list, ou entrée du scoring multi-proxy",
    )
    parser.add_argument(
        "--input-format",
        default="auto",
        choices=INPUT_FORMATS,
        help=(
            "Format du fichier --input-domains. "
            "auto=colonne domain ou URL si présente; "
            "grenouillemoi=colonne URL (ex. grenouillemoi.csv, 7e champ)"
        ),
    )

    parser.add_argument(
        "--tranco-csv",
        default=None,
        help="CSV Tranco local (rang,domaine). Si absent, téléchargement top-1m dans --cache-dir",
    )
    parser.add_argument(
        "--tranco-subdomains",
        action="store_true",
        help="Utiliser la liste Tranco incluant les sous-domaines (ZIP dédié)",
    )
    parser.add_argument(
        "--tranco-tld",
        default=None,
        help="Ne garder que les domaines se terminant par ce suffixe (ex: .fr ou fr)",
    )
    parser.add_argument(
        "--tranco-refresh",
        action="store_true",
        help="Forcer le re-téléchargement du ZIP Tranco (ignore le CSV en cache)",
    )
    parser.add_argument(
        "--tranco-list-only",
        action="store_true",
        help="Tranco seul : écrit le CSV à partir de la liste (pas de crawl ni score). Rapide pour grosses listes.",
    )
    parser.add_argument(
        "--preset",
        choices=["tranco-fr-10k"],
        default=None,
        help=(
            "tranco-fr-10k : 10 000 domaines .fr depuis Tranco, export direct "
            f"(sortie par défaut {PRESET_TRANCO_FR_10K_OUT}). Équivalent à "
            "--sources tranco --tranco-tld .fr --max-links 10000 --max-results 10000 --tranco-list-only."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Pages max à crawler par domaine (défaut: 5)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Lancer Chrome en headless (Google). Par défaut: fenêtre visible.",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy HTTP pour Google Playwright et pour le crawl de scoring (file_list)",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Connexion directe (sans proxy) pour le crawl de scoring file_list",
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        default=None,
        help="Port proxy local (ex: 101 -> http://127.0.0.1:101) pour Google ou scoring mono-worker",
    )
    parser.add_argument(
        "--capsolver-api-key",
        default=None,
        help="Clé API CapSolver pour résoudre automatiquement les captchas",
    )
    parser.add_argument(
        "--speed",
        default="fast",
        choices=["fast", "human"],
        help="Mode de saisie: 'fast' (rapide) ou 'human' (saisie caractère par caractère)",
    )
    parser.add_argument(
        "--google-reset-every-pages",
        type=int,
        default=0,
        help="Si >0, reset modem toutes les N pages Google (0 = désactivé, scrape jusqu'au captcha)",
    )
    parser.add_argument(
        "--google-resume-state-file",
        default="./.cache/seed_builder_prospects/google_resume_state.json",
        help="Fichier JSON de reprise pour Google (query/start en cours)",
    )
    parser.add_argument(
        "--google-start",
        type=int,
        default=None,
        help="Force un offset start Google (ex: 100) et ignore le fichier de reprise",
    )
    parser.add_argument(
        "--google-workers-map",
        default=None,
        help="Orchestrateur multi-workers Google. Format: '101:0,102:200,103:400,104:600'",
    )
    parser.add_argument(
        "--google-workers-parallel",
        type=int,
        default=0,
        help="Nombre max de workers Google en parallèle (<=0 = auto selon la taille de --google-workers-map)",
    )
    parser.add_argument(
        "--score-workers-map",
        default=None,
        help=(
            "Scoring CSV multi-proxy (source file_list seule). "
            "Format: '101:0,102:250,103:500,104:750' (port HTTP local -> index début dans le fichier). "
            "Chaque worker utilise http://127.0.0.1:PORT pour le crawl."
        ),
    )
    parser.add_argument(
        "--score-workers-ports",
        default=None,
        help=(
            "Scoring CSV multi-proxy simplifié (source file_list seule). "
            "Format: '101,102,103,104'. Le découpage du fichier unique est fait automatiquement."
        ),
    )
    parser.add_argument(
        "--score-workers-parallel",
        type=int,
        default=0,
        help=(
            "Nombre de workers scoring (et parallélisme max). "
            "En mode --score-workers-ports, permet d'ouvrir plusieurs workers par port "
            "(ex: 8 workers sur 4 ports => 2 workers/port). "
            "Avec --proxies-file: 0 = 1 worker par proxy du fichier. "
            "Sans --proxies-file ni ports/map: N workers en connexion directe (votre IP). "
            "0 = auto (1 worker par port en mode ports, ou 1 worker par entrée en mode map)."
        ),
    )
    parser.add_argument(
        "--proxies-file",
        default=None,
        help=(
            "Fichier de proxies (1 ligne = host:port:user:password). "
            "Ex: ./data/proxies.lightning.txt"
        ),
    )
    parser.add_argument(
        "--score-launch-terminals",
        action="store_true",
        help=(
            "Lance chaque worker scoring dans un terminal Windows séparé "
            "(au lieu du multithreading dans le même terminal). "
            "Attend la fin via des fichiers .done puis fusionne les CSV workers."
        ),
    )
    parser.add_argument(
        "--score-workers-run-dir",
        default=None,
        help="Dossier des sorties workers (.csv + .done) en mode --score-launch-terminals.",
    )
    parser.add_argument(
        "--score-worker-run",
        action="store_true",
        help="[Interne] Exécute un seul worker scoring (utilisé par l'orchestrateur terminaux).",
    )
    parser.add_argument(
        "--worker-slice",
        default=None,
        help="[Interne] Plage start:end dans --input-domains (ex: 0:2500).",
    )
    parser.add_argument(
        "--worker-out",
        default=None,
        help="[Interne] CSV de sortie du worker.",
    )
    parser.add_argument(
        "--worker-done",
        default=None,
        help="[Interne] Fichier marqueur de fin de worker.",
    )
    parser.add_argument("--delay-min", type=float, default=8)
    parser.add_argument("--delay-max", type=float, default=20)
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=60,
        help="Requêtes/min vers les domaines (défaut 60 = crawl rapide)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout HTTP secondes par requête (défaut 10)",
    )
    parser.add_argument(
        "--http-retries",
        type=int,
        default=3,
        help="Nombre de tentatives HTTP par URL (défaut 3).",
    )
    parser.add_argument(
        "--http-backoff",
        type=float,
        default=2.0,
        help="Backoff (secondes) entre retries HTTP (défaut 2.0).",
    )
    parser.add_argument(
        "--recruitment-only",
        action="store_true",
        help="Ne garder que les domaines avec signal recrutement (tags + filtre strict).",
    )
    parser.add_argument(
        "--segment-target",
        choices=["auto", "multinationale", "recruitment", "b2b_seller"],
        default="auto",
        help="Cible un segment métier précis (défaut: auto).",
    )
    parser.add_argument(
        "--segment-loose",
        action="store_true",
        help="N'exclut pas les domaines classés 'rejected' (mode permissif).",
    )
    parser.add_argument(
        "--segment-min-score-recruitment",
        type=int,
        default=30,
        help="Score minimal pour le segment recruitment (défaut: 30).",
    )
    parser.add_argument(
        "--segment-min-score-b2b-seller",
        type=int,
        default=60,
        help="Score minimal pour le segment b2b_seller (défaut: 60).",
    )
    parser.add_argument(
        "--segment-min-score-multinationale",
        type=int,
        default=50,
        help="Score minimal pour le segment multinationale (défaut: 50).",
    )
    parser.add_argument(
        "--split-input-domains-by-ports",
        default=None,
        help="Split --input-domains selon une liste de ports (ex: '101,102,103,104').",
    )
    parser.add_argument(
        "--split-input-domains-by-workers-map",
        default=None,
        help="Split --input-domains selon un workers-map (ex: '101:0,102:250,103:500').",
    )
    parser.add_argument(
        "--split-output-dir",
        default="./data",
        help="Dossier de sortie pour les fichiers split (défaut: ./data).",
    )
    parser.add_argument(
        "--split-only",
        action="store_true",
        help="Exécute uniquement le split et quitte.",
    )

    args = parser.parse_args()
    _apply_cli_preset(args)
    setup_logging(debug=args.debug)

    if getattr(args, "score_worker_run", False):
        for field in ("worker_slice", "worker_out", "worker_done", "input_domains"):
            if not getattr(args, field, None):
                raise SystemExit(f"--{field.replace('_', '-')} requis avec --score-worker-run")
        if not _proxy_server_from_args(args):
            raise SystemExit("--proxy requis avec --score-worker-run")
        _run_standalone_score_worker(args)
        return

    split_ports_raw = getattr(args, "split_input_domains_by_ports", None)
    split_map_raw = getattr(args, "split_input_domains_by_workers_map", None)
    if split_ports_raw or split_map_raw:
        input_domains = getattr(args, "input_domains", None)
        if not input_domains:
            raise SystemExit(
                "--input-domains requis avec --split-input-domains-by-ports/--split-input-domains-by-workers-map"
            )
        if split_ports_raw:
            ports = _parse_ports_csv(
                split_ports_raw, "--split-input-domains-by-ports"
            )
        else:
            ports = [
                port
                for port, _start in _parse_workers_map(
                    split_map_raw, "--split-input-domains-by-workers-map"
                )
            ]
        created = _split_input_domains_for_ports(
            input_path=input_domains,
            ports=ports,
            output_dir=args.split_output_dir,
        )
        logger.info("Split terminé: %d fichier(s) créés", len(created))
        for p in created:
            logger.info("  - %s", p.as_posix())
        if args.split_only:
            return

    if getattr(args, "preset", None) == "tranco-fr-10k":
        logger.info(
            "Preset tranco-fr-10k : %d domaines .fr, export sans crawl -> %s",
            PRESET_TRANCO_FR_10K_COUNT,
            args.out,
        )

    cache_dir = cache_dir_from_args(args)
    rate_limit_delay = 60.0 / max(1, args.rate_limit)

    # Déterminer la liste des sources à exécuter
    if getattr(args, "sources", None) and str(args.sources).strip():
        source_list = [s.strip() for s in args.sources.split(",") if s.strip()]
    elif getattr(args, "provider", None) and str(args.provider).strip():
        source_list = [args.provider.strip()]
    else:
        raise SystemExit(
            "Indiquez --sources (ex: google,tranco,file_list) ou --provider (rétrocompat)"
        )

    for s in source_list:
        if s not in SOURCES_AVAILABLE:
            raise SystemExit(
                f"Source inconnue: {s}. Valides: {', '.join(SOURCES_AVAILABLE)}"
            )

    # Fixer le nombre max de domaines à découvrir à max-links
    max_domains_to_scrape = getattr(args, "max_links", UNLIMITED_MAX)
    max_valid_results = getattr(args, "max_results", UNLIMITED_MAX)
    max_pages = getattr(args, "max_pages", 5)
    logger.info(
        "Limite de domaines à scraper: %s | Limite de résultats valides: %s | Pages max/domaine: %d | timeout=%ss retries=%d backoff=%ss",
        format_pipeline_limit(max_domains_to_scrape),
        format_pipeline_limit(max_valid_results),
        max_pages,
        args.timeout,
        args.http_retries,
        args.http_backoff,
    )

    # Mode orchestré Google: chaque worker fait sa découverte jusqu'au captcha,
    # puis son analyse locale, et on mutualise uniquement en fin de traitement.
    is_google_only = len(source_list) == 1 and source_list[0] == "google"
    if is_google_only and getattr(args, "google_workers_map", None):
        debug_records: list[dict] = []
        mapping = _parse_workers_map(args.google_workers_map, "--google-workers-map")
        configured_parallel = int(getattr(args, "google_workers_parallel", 0))
        if configured_parallel <= 0:
            workers_count = len(mapping)
        else:
            workers_count = min(len(mapping), configured_parallel)
        logger.info(
            "[GoogleOrchestrator] Mode analyse distribuée activé: %d worker(s), parallèle=%d",
            len(mapping),
            workers_count,
        )

        pack = QUERY_PACKS.get(args.query_pack)
        if not pack:
            raise SystemExit(f"query-pack inconnu: {args.query_pack}")
        queries = get_full_queries(pack)

        per_worker_discovery = (
            max(1, math.ceil(max_domains_to_scrape / len(mapping)))
            if not is_unlimited(max_domains_to_scrape)
            else 10**9
        )
        per_worker_scrape = (
            max(1, math.ceil(max_domains_to_scrape / len(mapping)))
            if not is_unlimited(max_domains_to_scrape)
            else 10**9
        )
        per_worker_valid = (
            max(1, math.ceil(max_valid_results / len(mapping)))
            if not is_unlimited(max_valid_results)
            else 10**9
        )

        all_rows: list[dict] = []
        all_debug_records: list[dict] = []
        worker_reports: list[_GoogleWorkerPipelineResult] = []

        with ThreadPoolExecutor(max_workers=workers_count) as pool:
            futures_map = {}
            for idx, (port, start) in enumerate(mapping, start=1):
                fut = pool.submit(
                    _run_google_worker_end_to_end,
                    idx,
                    port,
                    start,
                    queries,
                    args,
                    per_worker_discovery,
                    cache_dir,
                    args.min_score,
                    args.timeout,
                    rate_limit_delay,
                    max_pages,
                    per_worker_scrape,
                    per_worker_valid,
                )
                futures_map[fut] = (idx, port, start)

            for fut in as_completed(futures_map):
                idx, port, start = futures_map[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    logger.warning(
                        "[GoogleOrchestrator] Worker #%d (port=%d,start=%d) en erreur pipeline: %s",
                        idx,
                        port,
                        start,
                        e,
                    )
                    continue
                worker_reports.append(result)
                all_rows.extend(result.csv_rows)
                all_debug_records.extend(result.debug_records)
                logger.info(
                    "[GoogleOrchestrator] Worker #%d fini (port=%d,start=%d): découverts=%d, valides=%d",
                    idx,
                    port,
                    start,
                    result.discovered_count,
                    len(result.csv_rows),
                )

        csv_rows = _merge_csv_rows_by_domain(all_rows, max_valid_results)
        debug_records.extend(all_debug_records)
        logger.info(
            "[GoogleOrchestrator] Mutualisation finale: workers_ok=%d/%d | lignes_valides=%d (avant dédup=%d)",
            len(worker_reports),
            len(mapping),
            len(csv_rows),
            len(all_rows),
        )
        write_csv(args.out, csv_rows)
        logger.info("CSV écrit: %s (%d lignes)", args.out, len(csv_rows))
        if args.debug_jsonl:
            write_debug_jsonl(args.debug_jsonl, debug_records)
            logger.info("Debug JSONL écrit: %s", args.debug_jsonl)
        return

    # Scoring d'un CSV de domaines (file_list) réparti sur plusieurs proxies HTTP.
    is_file_list_score_workers = (
        len(source_list) == 1
        and source_list[0] == "file_list"
        and (
            getattr(args, "score_workers_map", None)
            or getattr(args, "score_workers_ports", None)
            or getattr(args, "proxies_file", None)
            or int(getattr(args, "score_workers_parallel", 0) or 0) > 0
        )
    )
    if is_file_list_score_workers:
        in_path = Path(getattr(args, "input_domains", "") or "")
        if not in_path.is_file():
            raise SystemExit(
                "--input-domains requis : chemin vers un CSV (colonne domain) ou TXT"
            )
        all_dr = load_discovery_from_seed_csv(
            in_path, input_format=getattr(args, "input_format", "auto")
        )
        n_total = len(all_dr)
        if n_total == 0:
            raise SystemExit(f"Aucun domaine lu depuis {in_path}")

        score_jobs = _build_score_jobs(args, n_total)
        if not score_jobs:
            raise SystemExit("Aucun job scoring construit")

        logger.info(
            "[ScoreOrchestrator] Fichier=%s | %d domaine(s) | %d worker(s) | terminaux=%s",
            in_path,
            n_total,
            len(score_jobs),
            bool(getattr(args, "score_launch_terminals", False)),
        )

        if getattr(args, "score_launch_terminals", False):
            run_dir = Path(
                args.score_workers_run_dir
                or f"./.cache/score_workers_run_{int(time.time())}"
            )
            run_dir.mkdir(parents=True, exist_ok=True)
            cwd = Path.cwd()
            worker_out_paths: list[Path] = []
            worker_done_paths: list[Path] = []

            for worker_id, http_proxy, start, end in score_jobs:
                out_p = run_dir / f"worker_{worker_id:02d}.csv"
                done_p = run_dir / f"worker_{worker_id:02d}.done"
                argv = _build_score_worker_cli_argv(
                    args, worker_id, http_proxy, start, end, out_p, done_p
                )
                title = f"ScoreWorker-{worker_id}"
                logger.info(
                    "[ScoreOrchestrator] Terminal %s | slice=%d:%d | proxy=%s",
                    title,
                    start,
                    end,
                    _proxy_label(http_proxy),
                )
                _launch_score_worker_terminal(argv, cwd, title)
                worker_out_paths.append(out_p)
                worker_done_paths.append(done_p)

            logger.info("[ScoreOrchestrator] Dossier workers: %s", run_dir)
            _wait_for_worker_done_files(worker_done_paths)
            csv_rows = _merge_score_worker_csv_outputs(
                worker_out_paths, max_valid_results
            )
            logger.info(
                "[ScoreOrchestrator] Mutualisation terminaux: lignes=%d",
                len(csv_rows),
            )
        else:
            score_rows, score_debug, score_reports = _run_score_jobs_in_threads(
                score_jobs, all_dr, args, cache_dir, max_pages, rate_limit_delay
            )
            csv_rows = _merge_csv_rows_by_domain(score_rows, max_valid_results)
            logger.info(
                "[ScoreOrchestrator] Mutualisation threads: workers_ok=%d/%d | lignes=%d",
                len(score_reports),
                len(score_jobs),
                len(csv_rows),
            )
            if args.debug_jsonl:
                write_debug_jsonl(args.debug_jsonl, score_debug)
                logger.info("Debug JSONL écrit: %s", args.debug_jsonl)

        write_csv(args.out, csv_rows)
        logger.info("CSV écrit: %s (%d lignes)", args.out, len(csv_rows))
        return

    # Découverte par source puis fusion + dédup
    # Passer directement max_domains_to_scrape à chaque source (pas de calcul)
    results_per_source: list[tuple[str, list[DiscoveryResult]]] = []
    total_discovered = 0

    for source_id in source_list:
        # Arrêter si on a déjà assez de domaines à scraper
        if limit_reached(total_discovered, max_domains_to_scrape):
            logger.info(
                "Limite de domaines à scraper atteinte (%s), arrêt de la découverte",
                format_pipeline_limit(max_domains_to_scrape),
            )
            break

        try:
            # Passer directement max_domains_to_scrape à la découverte (pas de calcul)
            # La découverte s'arrêtera automatiquement quand elle atteindra cette limite
            # On passe le nombre exact de domaines à découvrir, pas un calcul
            logger.info(
                "Démarrage découverte pour source %s (limite: %s domaines)",
                source_id,
                format_pipeline_limit(max_domains_to_scrape),
            )
            results = _run_discovery_single_source(
                source_id, args, max_domains_to_scrape
            )
            results_per_source.append((source_id, results))
            total_discovered += len(results)
            logger.info(
                "Source %s: %d candidats (total découvert: %d/%s)",
                source_id,
                len(results),
                total_discovered,
                format_pipeline_limit(max_domains_to_scrape),
            )

            # Arrêter si on a atteint la limite (la découverte devrait déjà s'être arrêtée, mais on vérifie)
            if limit_reached(total_discovered, max_domains_to_scrape):
                logger.info(
                    "Limite de domaines à scraper atteinte (%s), arrêt de la découverte",
                    format_pipeline_limit(max_domains_to_scrape),
                )
                break
        except SystemExit as e:
            raise
        except Exception as e:
            logger.warning("Source %s en erreur: %s", source_id, e)

    discovery_results = _merge_and_dedupe(results_per_source, max_domains_to_scrape)
    logger.info(
        "Découverte totale (après dédup): %d candidats (limite scraper: %s)",
        len(discovery_results),
        format_pipeline_limit(max_domains_to_scrape),
    )

    if getattr(args, "tranco_list_only", False):
        if source_list != ["tranco"]:
            raise SystemExit(
                "--tranco-list-only (ou preset tranco-fr-10k) : utilisez uniquement la source "
                "tranco, ex. --sources tranco ou --preset tranco-fr-10k."
            )
        csv_rows = _csv_rows_from_discovery_list_only(
            discovery_results, max_rows=max_valid_results
        )
        if not is_unlimited(max_valid_results) and len(csv_rows) < max_valid_results:
            logger.warning(
                "Tranco .fr : %d domaines obtenus (cible %d). Le top 1M contient un nombre fini de .fr.",
                len(csv_rows),
                max_valid_results,
            )
        write_csv(args.out, csv_rows)
        logger.info(
            "CSV écrit (tranco, sans crawl): %s (%d lignes)",
            args.out,
            len(csv_rows),
        )
        if args.debug_jsonl:
            dbg = [
                debug_record(
                    r["domain"],
                    excluded=False,
                    exclusion_reason=None,
                    final_score=0,
                    signals={"mode": "tranco_list_only", "evidence": r.get("evidence", "")},
                )
                for r in csv_rows
            ]
            write_debug_jsonl(args.debug_jsonl, dbg)
            logger.info("Debug JSONL écrit: %s", args.debug_jsonl)
        return

    debug_records: list[dict] = []
    http_proxy_single = None if getattr(args, "no_proxy", False) else _proxy_server_from_args(args)
    csv_rows = _run_pipeline(
        discovery_results,
        cache_dir=cache_dir,
        min_score=args.min_score,
        timeout=args.timeout,
        rate_limit_delay=rate_limit_delay,
        http_retries=int(getattr(args, "http_retries", 3)),
        http_backoff=float(getattr(args, "http_backoff", 2.0)),
        max_pages_per_domain=max_pages,
        max_domains_to_scrape=max_domains_to_scrape,
        max_valid_results=max_valid_results,
        debug_records=debug_records,
        http_proxy=http_proxy_single,
        recruitment_only=bool(getattr(args, "recruitment_only", False)),
        segment_target=str(getattr(args, "segment_target", "auto")),
        segment_strict=not bool(getattr(args, "segment_loose", False)),
        segment_min_score_recruitment=int(
            getattr(args, "segment_min_score_recruitment", 30)
        ),
        segment_min_score_b2b_seller=int(
            getattr(args, "segment_min_score_b2b_seller", 60)
        ),
        segment_min_score_multinationale=int(
            getattr(args, "segment_min_score_multinationale", 50)
        ),
    )

    # Output
    write_csv(args.out, csv_rows)
    logger.info("CSV écrit: %s (%d lignes)", args.out, len(csv_rows))
    if args.debug_jsonl:
        write_debug_jsonl(args.debug_jsonl, debug_records)
        logger.info("Debug JSONL écrit: %s", args.debug_jsonl)


if __name__ == "__main__":
    main()
