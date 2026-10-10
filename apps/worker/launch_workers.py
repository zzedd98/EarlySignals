"""
Lance N workers signaux dans des terminaux séparés et affiche un résumé.

Usage (depuis apps/worker) :
  python launch_workers.py
  python launch_workers.py --count 10
  python launch_workers.py --count 10 --idle-polls 2
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from orchestrator_stats import (
    print_worker_orchestrator_summary,
    wait_for_all_workers,
)

WORKER_DIR = Path(__file__).resolve().parent
API_VENV_PYTHON = WORKER_DIR.parent / "api" / "venv" / "Scripts" / "python.exe"
RUNS_DIR = WORKER_DIR / ".orchestrator-runs"
CREATE_NEW_CONSOLE = 0x00000010


def _create_run_id() -> str:
    return f"worker-{int(time.time() * 1000)}"


def _prepare_stats_dir(run_id: str) -> Path:
    stats_dir = RUNS_DIR / run_id
    stats_dir.mkdir(parents=True, exist_ok=True)
    return stats_dir


def _resolve_python() -> Path:
    if API_VENV_PYTHON.exists():
        return API_VENV_PYTHON
    return Path(sys.executable)


def spawn_worker(
    worker_index: int,
    *,
    run_id: str,
    stats_dir: Path,
    idle_polls: int,
    python_exe: Path,
) -> None:
    """Lance un terminal cmd dédié (même pattern que apps/scraper launchWorkers.ts)."""
    bat_path = stats_dir / f"run-worker-{worker_index}.bat"
    bat_content = "\r\n".join(
        [
            "@echo off",
            f"title SignalWorker-{worker_index}",
            "echo.",
            f"echo ===== SignalWorker-{worker_index} =====",
            f'cd /d "{WORKER_DIR}"',
            f'set "WORKER_ORCHESTRATOR_RUN_ID={run_id}"',
            f'set "WORKER_ORCHESTRATOR_STATS_DIR={stats_dir}"',
            f'set "WORKER_ID={worker_index}"',
            f'set "WORKER_IDLE_POLLS_TO_FINISH={idle_polls}"',
            f'"{python_exe}" main.py',
            "echo.",
            f"echo [SignalWorker-{worker_index}] Termine (code %ERRORLEVEL%).",
            "pause",
        ]
    )
    bat_path.write_text(bat_content, encoding="utf-8")

    # CREATE_NEW_CONSOLE : nouvelle fenetre cmd sans la commande start (evite les bugs de quoting)
    subprocess.Popen(
        ["cmd.exe", "/k", str(bat_path)],
        cwd=str(WORKER_DIR),
        creationflags=CREATE_NEW_CONSOLE,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lance des workers signaux en parallèle (Windows)."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Nombre de workers (défaut: 10)",
    )
    parser.add_argument(
        "--idle-polls",
        type=int,
        default=2,
        help="Tours à vide avant fin d'un worker (défaut: 2 × 15s)",
    )
    args = parser.parse_args()

    if args.count < 1:
        print("ERREUR: --count doit etre >= 1")
        return 1

    if sys.platform != "win32":
        print("ERREUR: launch_workers.py est prevu pour Windows (cmd).")
        return 1

    python_exe = _resolve_python()
    if not python_exe.exists():
        print(f"ERREUR: Python introuvable: {python_exe}")
        print("   Active le venv API: cd apps\\api && .\\venv\\Scripts\\activate")
        return 1

    run_id = _create_run_id()
    stats_dir = _prepare_stats_dir(run_id)

    print("\nOrchestrateur workers signaux")
    print(f"   Workers        : {args.count}")
    print(f"   Idle polls     : {args.idle_polls} (~{args.idle_polls * 15}s sans snapshot)")
    print(f"   Python         : {python_exe}")
    print(f"   Stats          : {stats_dir}")
    print("")

    for i in range(args.count):
        spawn_worker(
            i,
            run_id=run_id,
            stats_dir=stats_dir,
            idle_polls=args.idle_polls,
            python_exe=python_exe,
        )
        print(f"   OK SignalWorker-{i} lance")
        time.sleep(0.3)

    print("\nEn attente de la fin des workers...")

    def on_progress(done: int, total: int) -> None:
        print(f"   ... {done}/{total} worker(s) termine(s)", end="\r")

    results = wait_for_all_workers(
        str(stats_dir),
        args.count,
        poll_interval_sec=2.0,
        on_progress=on_progress,
    )
    print()

    print_worker_orchestrator_summary(
        results,
        run_id=run_id,
        worker_count=args.count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
