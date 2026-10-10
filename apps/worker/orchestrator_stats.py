"""Stats d'orchestration multi-workers (fichiers JSON partagés)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class WorkerRunStats:
    worker_index: int
    status: str  # completed | error
    snapshots_processed: int
    signals_saved: int
    opportunities_created: int
    errors: int
    batches: int
    duration_ms: int
    finished_at: str
    error_message: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_orchestrator_context() -> Optional[dict[str, Any]]:
    stats_dir = os.getenv("WORKER_ORCHESTRATOR_STATS_DIR", "").strip()
    run_id = os.getenv("WORKER_ORCHESTRATOR_RUN_ID", "").strip()
    worker_id = os.getenv("WORKER_ID", "").strip()

    if not stats_dir or not run_id:
        return None

    try:
        worker_index = int(worker_id) if worker_id else 0
    except ValueError:
        worker_index = 0

    return {
        "stats_dir": stats_dir,
        "run_id": run_id,
        "worker_index": worker_index,
    }


def worker_stats_path(stats_dir: str, worker_index: int) -> Path:
    return Path(stats_dir) / f"worker-{worker_index}.json"


def write_worker_stats(stats_dir: str, worker_index: int, stats: WorkerRunStats) -> None:
    path = worker_stats_path(stats_dir, worker_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(stats), indent=2), encoding="utf-8")


def read_worker_stats(file_path: Path) -> Optional[WorkerRunStats]:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return WorkerRunStats(**data)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def wait_for_all_workers(
    stats_dir: str,
    expected_count: int,
    poll_interval_sec: float = 2.0,
    on_progress: Optional[Any] = None,
) -> list[WorkerRunStats]:
    stats_path = Path(stats_dir)
    results: dict[int, WorkerRunStats] = {}

    while len(results) < expected_count:
        for i in range(expected_count):
            if i in results:
                continue
            file_path = worker_stats_path(stats_dir, i)
            if not file_path.exists():
                continue
            stats = read_worker_stats(file_path)
            if stats:
                results[i] = stats

        if on_progress:
            on_progress(len(results), expected_count)

        if len(results) < expected_count:
            import time

            time.sleep(poll_interval_sec)

    return [results[i] for i in range(expected_count)]


def print_worker_orchestrator_summary(
    results: list[WorkerRunStats],
    *,
    run_id: str,
    worker_count: int,
) -> None:
    totals = {
        "snapshots_processed": sum(r.snapshots_processed for r in results),
        "signals_saved": sum(r.signals_saved for r in results),
        "opportunities_created": sum(r.opportunities_created for r in results),
        "errors": sum(r.errors for r in results),
        "batches": sum(r.batches for r in results),
        "duration_ms": max((r.duration_ms for r in results), default=0),
        "failed_workers": sum(1 for r in results if r.status == "error"),
    }

    print("\n" + "=" * 50)
    print("RESUME ORCHESTRATEUR WORKERS")
    print("=" * 50)
    print(f"   Run ID              : {run_id}")
    print(f"   Workers             : {worker_count}")
    print("-" * 50)
    print(f"   Snapshots traités   : {totals['snapshots_processed']}")
    print(f"   Signaux enregistrés : {totals['signals_saved']}")
    print(f"   Opportunités créées : {totals['opportunities_created']}")
    print(f"   Erreurs snapshot    : {totals['errors']}")
    print(f"   Batches             : {totals['batches']}")
    if totals["failed_workers"]:
        print(f"   Workers en erreur   : {totals['failed_workers']}")
    print(f"   Durée max worker    : {totals['duration_ms'] / 1000:.1f}s")
    print("-" * 50)
    for r in results:
        icon = "X" if r.status == "error" else "OK"
        print(
            f"   {icon} Worker #{r.worker_index} — "
            f"{r.snapshots_processed} snapshot(s), "
            f"{r.opportunities_created} opportunité(s) "
            f"({r.duration_ms / 1000:.1f}s)"
        )
        if r.error_message:
            print(f"      -> {r.error_message}")
    print("=" * 50)
    print("Les fenêtres workers restent ouvertes (pause).\n")
