#!/usr/bin/env python3
"""
Extrait les domaines des startups depuis l'annuaire Les Pépites Tech.

Source : https://lespepitestech.com/startup/france
~11 147 startups, 10 par page, pagination ?page=0 … ?page=1114.

Usage single worker :
  python scripts/scrape_lespepitestech_domains.py --start-page 0 --end-page 111

Multi-workers (10 terminaux + proxies Lightning) :
  python scripts/scrape_lespepitestech_domains.py --launch-terminals --worker-count 10

Fusion apres run :
  python scripts/scrape_lespepitestech_domains.py --merge

Import API :
  python scripts/import_seed_to_api.py data/lespepitestech_domains.csv ...
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seed_builder_prospects.crawl.url_normalize import canonical_domain_from_url
from seed_builder_prospects.proxy_config import load_proxies_from_file

BASE_URL = "https://lespepitestech.com"
LISTING_PATH = "/startup/france"
DETAIL_PREFIX = "/startup-de-la-french-tech/"
UTM_MARKER = "utm_source=LesPepitesTech.com"
DEFAULT_WORKER_DIR = ROOT / "data" / "lespepitestech_workers"
DEFAULT_MERGED_OUTPUT = ROOT / "data" / "lespepitestech_domains.csv"
DEFAULT_PROXIES_FILE = ROOT / "data" / "proxies.lightning.txt"
CSV_FIELDS = ["domain", "name", "slug", "website_url", "pepites_url", "list_page", "worker_index"]

CREATE_NEW_CONSOLE = 0x00000010

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

BLOCKED_HOST_SUFFIXES = (
    "lespepitestech.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "google.com",
    "instagram.com",
)


@dataclass
class StartupRecord:
    domain: str
    name: str
    slug: str
    website_url: str
    pepites_url: str
    list_page: int
    worker_index: int = -1


@dataclass
class Checkpoint:
    processed_slugs: list[str]
    last_completed_page: int

    @classmethod
    def load(cls, path: Path) -> Checkpoint:
        if not path.is_file():
            return cls(processed_slugs=[], last_completed_page=-1)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            processed_slugs=list(data.get("processed_slugs", [])),
            last_completed_page=int(data.get("last_completed_page", -1)),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def mask_proxy_url(proxy_url: str) -> str:
    try:
        u = urlparse(proxy_url)
        host = u.hostname or ""
        if u.port:
            host = f"{host}:{u.port}"
        return f"***@{host}" if u.username else host
    except Exception:
        return "***"


def worker_paths(worker_dir: Path, worker_index: int) -> dict[str, Path]:
    base = worker_dir / f"worker_{worker_index}"
    return {
        "output": base / "domains.csv",
        "checkpoint": base / "checkpoint.json",
        "errors": base / "errors.tsv",
    }


def page_range_for_worker(
    last_page: int, worker_index: int, worker_count: int
) -> tuple[int, int] | None:
    total_pages = last_page + 1
    per_worker = math.ceil(total_pages / worker_count)
    start = worker_index * per_worker
    end = min(start + per_worker - 1, last_page)
    if start > last_page:
        return None
    return start, end


def listing_url(page: int) -> str:
    if page <= 0:
        return f"{BASE_URL}{LISTING_PATH}"
    return f"{BASE_URL}{LISTING_PATH}?page={page}"


def build_http_client(proxy_url: str | None) -> httpx.Client:
    kwargs: dict = {
        "headers": DEFAULT_HEADERS,
        "follow_redirects": True,
    }
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.Client(**kwargs)


def fetch_html(client: httpx.Client, url: str, retries: int = 3) -> str:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.get(url, timeout=45.0)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"Echec GET {url}: {last_err}") from last_err


def parse_listing_slugs(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    for row in soup.select(".views-row"):
        detail_href = None
        name = ""
        for a in row.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(DETAIL_PREFIX):
                detail_href = href
                break
        if not detail_href:
            continue

        slug = detail_href[len(DETAIL_PREFIX) :].strip().strip("/")
        if not slug or slug in seen:
            continue

        heading = row.find(["h2", "h3", "h4"])
        if heading:
            name = heading.get_text(strip=True)
        if not name:
            for a in row.find_all("a", href=True):
                t = a.get_text(strip=True)
                if t and not t.startswith("+") and "VOTER" not in t.upper():
                    name = t
                    break

        seen.add(slug)
        out.append((slug, name or slug))

    return out


def is_blocked_external(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return True
    if not host:
        return True
    return any(host == s or host.endswith("." + s) for s in BLOCKED_HOST_SUFFIXES)


def extract_website_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        text = re.sub(r"\s+", " ", a.get_text(strip=True)).lower()
        if UTM_MARKER in href or "visiter leur site" in text or "visiter" in text:
            if not is_blocked_external(href):
                candidates.append(href)

    if not candidates:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("http://", "https://")) and UTM_MARKER in href:
                if not is_blocked_external(href):
                    candidates.append(href)

    return candidates[0] if candidates else None


def domain_from_website_url(url: str) -> str:
    clean = url.split("#")[0]
    if "?" in clean:
        base, query = clean.split("?", 1)
        if any(p.startswith("utm_") for p in query.split("&")):
            clean = base
    domain = canonical_domain_from_url(clean)
    if not domain:
        domain = canonical_domain_from_url(url)
    return domain


def detect_last_page(client: httpx.Client) -> int:
    html = fetch_html(client, listing_url(0))
    soup = BeautifulSoup(html, "html.parser")
    max_page = 0
    for a in soup.find_all("a", href=True):
        m = re.search(r"[?&]page=(\d+)", a["href"])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


def load_existing_domains(csv_path: Path) -> set[str]:
    if not csv_path.is_file():
        return set()
    domains: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("domain") or "").strip().lower()
            if d:
                domains.add(d)
    return domains


def append_csv_row(csv_path: Path, record: StartupRecord, write_header: bool) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "domain": record.domain,
                "name": record.name,
                "slug": record.slug,
                "website_url": record.website_url,
                "pepites_url": record.pepites_url,
                "list_page": record.list_page,
                "worker_index": record.worker_index,
            }
        )


def scrape(
    output: Path,
    checkpoint_path: Path,
    errors_path: Path,
    start_page: int,
    end_page: int | None,
    delay: float,
    resume: bool,
    proxy_url: str | None,
    worker_index: int | None,
) -> None:
    checkpoint = Checkpoint.load(checkpoint_path) if resume else Checkpoint([], -1)
    processed_slugs = set(checkpoint.processed_slugs)
    known_domains = load_existing_domains(output) if resume else set()
    write_header = not output.is_file() or output.stat().st_size == 0
    stats = {"domains": 0, "skipped_slug": 0, "no_website": 0, "errors": 0}
    wid = worker_index if worker_index is not None else -1
    proxy_label = mask_proxy_url(proxy_url) if proxy_url else "direct"

    with build_http_client(proxy_url) as client:
        if end_page is None:
            end_page = detect_last_page(client)
            print(f"Derniere page detectee : {end_page} (0-indexee)")

        page_start = max(0, start_page)
        if resume and checkpoint.last_completed_page >= 0:
            page_start = max(page_start, checkpoint.last_completed_page + 1)

        if page_start > end_page:
            print(f"Worker {wid}: rien a faire (pages {page_start}-{end_page} deja faites)")
            return

        print(
            f"Worker {wid} | proxy={proxy_label} | pages {page_start}-{end_page} | "
            f"{len(processed_slugs)} slug(s) deja vus | {len(known_domains)} domaine(s) CSV"
        )

        for page in tqdm(range(page_start, end_page + 1), desc=f"W{wid} pages", unit="page"):
            html = fetch_html(client, listing_url(page))
            startups = parse_listing_slugs(html)

            for slug, name in tqdm(
                startups,
                desc=f"  W{wid} p{page}",
                leave=False,
                unit="startup",
            ):
                if slug in processed_slugs:
                    stats["skipped_slug"] += 1
                    continue

                pepites_url = f"{BASE_URL}{DETAIL_PREFIX}{slug}"
                try:
                    detail_html = fetch_html(client, pepites_url)
                    website_url = extract_website_url(detail_html)
                    if not website_url:
                        stats["no_website"] += 1
                        with errors_path.open("a", encoding="utf-8") as ef:
                            ef.write(f"{slug}\t{name}\tno_website\t{pepites_url}\n")
                        processed_slugs.add(slug)
                        continue

                    domain = domain_from_website_url(website_url)
                    if not domain:
                        stats["no_website"] += 1
                        with errors_path.open("a", encoding="utf-8") as ef:
                            ef.write(f"{slug}\t{name}\tbad_url\t{website_url}\n")
                        processed_slugs.add(slug)
                        continue

                    if domain not in known_domains:
                        record = StartupRecord(
                            domain=domain,
                            name=name,
                            slug=slug,
                            website_url=website_url,
                            pepites_url=pepites_url,
                            list_page=page,
                            worker_index=wid,
                        )
                        append_csv_row(output, record, write_header)
                        write_header = False
                        known_domains.add(domain)
                        stats["domains"] += 1

                    processed_slugs.add(slug)
                    if delay > 0:
                        time.sleep(delay)

                except Exception as exc:
                    stats["errors"] += 1
                    with errors_path.open("a", encoding="utf-8") as ef:
                        ef.write(f"{slug}\t{name}\terror\t{exc}\n")
                    tqdm.write(f"WARN W{wid} {slug}: {exc}")

            checkpoint.processed_slugs = sorted(processed_slugs)
            checkpoint.last_completed_page = page
            checkpoint.save(checkpoint_path)

            if delay > 0:
                time.sleep(delay)

    print(
        f"\nWorker {wid} termine — {stats['domains']} nouveau(x) domaine(s) -> {output}\n"
        f"   slugs deja vus: {stats['skipped_slug']}\n"
        f"   sans site: {stats['no_website']}\n"
        f"   erreurs: {stats['errors']}\n"
        f"   total domaines uniques: {len(known_domains)}"
    )


def merge_worker_outputs(worker_dir: Path, merged_output: Path) -> None:
    """Fusionne worker_*/domains.csv en un CSV deduplique par domaine."""
    worker_csvs = sorted(worker_dir.glob("worker_*/domains.csv"))
    if not worker_csvs:
        raise SystemExit(f"Aucun CSV worker dans {worker_dir}")

    by_domain: dict[str, dict[str, str]] = {}
    total_rows = 0

    for csv_path in worker_csvs:
        with csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_rows += 1
                domain = (row.get("domain") or "").strip().lower()
                if not domain:
                    continue
                if domain not in by_domain:
                    by_domain[domain] = row

    merged_output.parent.mkdir(parents=True, exist_ok=True)
    with merged_output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for domain in sorted(by_domain.keys()):
            writer.writerow(by_domain[domain])

    print(
        f"Fusion OK: {len(by_domain)} domaines uniques "
        f"(depuis {total_rows} lignes, {len(worker_csvs)} workers) -> {merged_output}"
    )


def launch_worker_terminals(
    worker_count: int,
    worker_dir: Path,
    proxies_file: Path,
    delay: float,
    resume: bool,
    last_page: int | None,
) -> None:
    script_path = Path(__file__).resolve()
    project_dir = ROOT

    proxies: list[str] = []
    if proxies_file.is_file():
        proxies = load_proxies_from_file(proxies_file)
    else:
        print(f"WARN: pas de proxy ({proxies_file}) — crawl en IP directe")

    with build_http_client(proxies[0] if proxies else None) as client:
        if last_page is None:
            last_page = detect_last_page(client)

    print("\nOrchestrateur Les Pepites Tech")
    print(f"   Derniere page: {last_page}")
    print(f"   Workers: {worker_count}")
    print(f"   Sortie: {worker_dir}/worker_N/domains.csv")
    if proxies:
        print(f"   Proxies: {len(proxies)} (1 fixe par worker)")
    print("")

    resume_flag = "--resume" if resume else "--no-resume"

    for i in range(worker_count):
        page_range = page_range_for_worker(last_page, i, worker_count)
        if page_range is None:
            continue
        start_page, end_page = page_range
        window_title = f"PepitesWorker-{i}"
        proxy_label = mask_proxy_url(proxies[i % len(proxies)]) if proxies else "direct"

        cmd_parts = [
            "python",
            str(script_path),
            "--worker-index",
            str(i),
            "--worker-count",
            str(worker_count),
            "--start-page",
            str(start_page),
            "--end-page",
            str(end_page),
            "--worker-dir",
            str(worker_dir),
            "--delay",
            str(delay),
            resume_flag,
        ]
        if proxies_file.is_file():
            cmd_parts.extend(["--proxies-file", str(proxies_file)])

        run_cmd = subprocess.list2cmdline(cmd_parts)
        inner_script = " & ".join(
            [
                "@echo off",
                f"cd /d \"{project_dir}\"",
                f"title {window_title}",
                "echo.",
                f"echo ===== {window_title} =====",
                f"echo pages={start_page}-{end_page} proxy={proxy_label}",
                "echo.",
                run_cmd,
                "echo.",
                f"echo [{window_title}] Termine (code %ERRORLEVEL%).",
                "pause",
            ]
        )

        if sys.platform == "win32":
            subprocess.Popen(
                ["cmd.exe", "/k", inner_script],
                cwd=str(project_dir),
                creationflags=CREATE_NEW_CONSOLE,
                close_fds=True,
            )
        else:
            subprocess.Popen(
                ["bash", "-lc", f'cd "{project_dir}" && {run_cmd}; read -p "Entree..." _'],
                cwd=str(project_dir),
                start_new_session=True,
            )

        print(
            f"   OK {window_title} -> pages {start_page}-{end_page} (~{end_page - start_page + 1} pages), proxy={proxy_label}"
        )

    print(
        f"\n{worker_count} terminal(aux) lance(s).\n"
        f"Quand tous sont finis, fusionnez :\n"
        f"  python scripts/scrape_lespepitestech_domains.py --merge "
        f"--worker-dir {worker_dir}\n"
    )


def resolve_proxy(proxies_file: Path | None, worker_index: int | None) -> str | None:
    if worker_index is None or proxies_file is None or not proxies_file.is_file():
        return None
    proxies = load_proxies_from_file(proxies_file)
    if not proxies:
        return None
    return proxies[worker_index % len(proxies)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extraire les domaines depuis lespepitestech.com/startup/france",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV de sortie (mode single-worker)",
    )
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--errors", type=Path, default=None)
    parser.add_argument("--worker-dir", type=Path, default=DEFAULT_WORKER_DIR)
    parser.add_argument("--worker-index", type=int, default=None)
    parser.add_argument("--worker-count", type=int, default=10)
    parser.add_argument("--start-page", type=int, default=0)
    parser.add_argument("--end-page", type=int, default=None)
    parser.add_argument("--last-page", type=int, default=None, help="Pour l'orchestrateur")
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--proxies-file", type=Path, default=DEFAULT_PROXIES_FILE)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--launch-terminals",
        action="store_true",
        help="Ouvre N terminaux Windows (1 worker chacun)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Fusionne worker_*/domains.csv en un seul CSV",
    )
    parser.add_argument(
        "--merged-output",
        type=Path,
        default=DEFAULT_MERGED_OUTPUT,
        help="CSV final apres --merge",
    )
    args = parser.parse_args()

    if args.merge:
        merge_worker_outputs(args.worker_dir, args.merged_output)
        return

    resume = bool(args.resume) and not args.no_resume

    if args.launch_terminals:
        launch_worker_terminals(
            worker_count=max(1, args.worker_count),
            worker_dir=args.worker_dir,
            proxies_file=args.proxies_file,
            delay=args.delay,
            resume=resume,
            last_page=args.last_page,
        )
        return

    # Mode worker multi : chemins par worker_index
    if args.worker_index is not None:
        paths = worker_paths(args.worker_dir, args.worker_index)
        output = args.output or paths["output"]
        checkpoint_path = args.checkpoint or paths["checkpoint"]
        errors_path = args.errors or paths["errors"]

        if args.end_page is None and args.worker_count:
            with build_http_client(None) as client:
                last = detect_last_page(client)
            pr = page_range_for_worker(last, args.worker_index, args.worker_count)
            if pr is None:
                print(f"Worker {args.worker_index}: aucune page assignee")
                return
            start_page, end_page = pr
        else:
            start_page = args.start_page
            end_page = args.end_page if args.end_page is not None else args.start_page

        proxy_url = resolve_proxy(args.proxies_file, args.worker_index)
        scrape(
            output=output,
            checkpoint_path=checkpoint_path,
            errors_path=errors_path,
            start_page=start_page,
            end_page=end_page,
            delay=args.delay,
            resume=resume,
            proxy_url=proxy_url,
            worker_index=args.worker_index,
        )
        return

    # Mode single-worker legacy
    output = args.output or DEFAULT_MERGED_OUTPUT
    checkpoint_path = args.checkpoint or ROOT / "data" / "lespepitestech_scrape.checkpoint.json"
    errors_path = args.errors or ROOT / "data" / "lespepitestech_scrape.errors.tsv"
    scrape(
        output=output,
        checkpoint_path=checkpoint_path,
        errors_path=errors_path,
        start_page=args.start_page,
        end_page=args.end_page,
        delay=args.delay,
        resume=resume,
        proxy_url=resolve_proxy(args.proxies_file, 0),
        worker_index=None,
    )


if __name__ == "__main__":
    main()
