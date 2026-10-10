"""
Early Signals Worker - Process snapshots, detect signals, create opportunities
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
import hashlib
import json
from pathlib import Path
import sys

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, and_, or_, desc
from meilisearch import Client as MeiliClient

# Ensure the FastAPI 'app' package (apps/api/app) is importable when running the worker directly
ROOT_DIR = Path(__file__).resolve().parents[2]
API_APP_DIR = ROOT_DIR / "apps" / "api"
if str(API_APP_DIR) not in sys.path:
    sys.path.insert(0, str(API_APP_DIR))

from app.models.domain import Domain
from app.models.snapshot import DomainSnapshot
from app.models.signal import Signal
from app.models.opportunity import Opportunity
from app.core.signal_importance import (
    format_signal_log_prefix,
    resolve_signal_importance,
    signal_log_icon,
    IMPORTANCE_RANK,
)
from config import config
from signal_detector import SignalDetector
from scorer import Scorer
from llm_enricher import LLMEnricher
from notifier import notify_opportunity_created
from change_analyzer import ChangeAnalyzer
from change_describer import describe_signal_change
from orchestrator_stats import (
    WorkerRunStats,
    get_orchestrator_context,
    write_worker_stats,
)

# Database setup
engine = create_async_engine(
    config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Meilisearch client
meili_client = MeiliClient(config.MEILI_URL, config.MEILI_MASTER_KEY)


def _truncate_change_summary(text: str, max_len: int = 120) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


async def get_pending_snapshots(
    session: AsyncSession, limit: int = 10
) -> List[DomainSnapshot]:
    """
    Récupère un batch de snapshots à traiter, en les verrouillant pour
    qu'un seul worker puisse les prendre (FOR UPDATE SKIP LOCKED).

    Un snapshot est considéré comme "à traiter" si:
    - extracted_json est NULL (ancien comportement), ou
    - extracted_json existe mais ne contient pas de champ "processed" à True
      (cas des snapshots créés par le scraper avec seulement des métadonnées).
    """
    stmt = (
        select(DomainSnapshot)
        .where(
            or_(
                DomainSnapshot.extracted_json.is_(None),
                # JSON sans champ "processed" (ou explicitement False) = pas encore traité par le worker
                DomainSnapshot.extracted_json["processed"].astext.is_(None),
                DomainSnapshot.extracted_json["processed"].astext == "false",
            )
        )
        .order_by(DomainSnapshot.fetched_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def has_content_changed(
    snapshot: DomainSnapshot, session: AsyncSession
) -> Tuple[bool, bool, Optional[DomainSnapshot]]:
    """
    Compare ce snapshot au précédent pour la même URL, en se basant sur fetched_at.

    Retourne (has_changed, is_first_snapshot, previous_snapshot):
    - has_changed: True si le contenu a changé par rapport au snapshot précédent
    - is_first_snapshot: True si c'est le premier snapshot chronologique pour cette URL
      (aucun snapshot avec fetched_at < snapshot.fetched_at)
    - previous_snapshot: le snapshot précédent (None si premier snapshot)
    """
    # Récupérer le snapshot immédiatement précédent (même domaine + URL, fetched_at strictement plus ancien)
    result = await session.execute(
        select(DomainSnapshot)
        .where(
            and_(
                DomainSnapshot.domain_id == snapshot.domain_id,
                DomainSnapshot.url == snapshot.url,
                DomainSnapshot.id != snapshot.id,  # Exclude current snapshot
                DomainSnapshot.fetched_at < snapshot.fetched_at,
            )
        )
        .order_by(DomainSnapshot.fetched_at.desc())
        .limit(1)
    )
    last_snapshot = result.scalar_one_or_none()

    # If no previous snapshot exists, this is the first snapshot
    if not last_snapshot:
        return (
            False,
            True,
            None,
        )  # No change detected (can't compare), but it's the first snapshot

    # Compare hashes
    if not snapshot.hash or not last_snapshot.hash:
        # If hash is missing, assume content changed (shouldn't happen, but safety check)
        return (True, False, last_snapshot)

    # Content changed if hash is different
    has_changed = snapshot.hash != last_snapshot.hash
    return (has_changed, False, last_snapshot)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def detect_signals(
    snapshot: DomainSnapshot,
    previous_snapshot: Optional[DomainSnapshot] = None,
    change_analysis: Optional[dict] = None,
) -> List[Signal]:
    """Detect signals from a snapshot, optionally comparing with the previous snapshot"""
    detector = SignalDetector()
    signals = await detector.detect(
        snapshot, previous_snapshot, change_analysis=change_analysis
    )
    return signals


async def _mark_snapshot_error(snapshot_id, error_message: str) -> None:
    """Marque un snapshot en erreur pour éviter de le retraiter indéfiniment."""
    async with AsyncSessionLocal() as session:
        snap = await session.get(DomainSnapshot, snapshot_id)
        if not snap:
            return
        meta = dict(snap.extracted_json or {})
        meta.update(
            {
                "processed": True,
                "processed_at": _utc_now_iso(),
                "error": error_message[:500],
                "reason": "processing_error",
            }
        )
        snap.extracted_json = meta
        await session.commit()


async def deduplicate_signal(signal: Signal, session: AsyncSession) -> bool:
    """Check if signal already exists (deduplication)"""
    # Check for similar signal in last 7 days
    seven_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)

    result = await session.execute(
        select(Signal).where(
            and_(
                Signal.domain_id == signal.domain_id,
                Signal.type == signal.type,
                Signal.proof_url == signal.proof_url,
                Signal.detected_at >= seven_days_ago,
            )
        )
    )
    existing = result.scalar_one_or_none()
    return existing is None


async def create_opportunity(
    signal: Signal,
    domain: Domain,
    session: AsyncSession,
    scorer: Scorer,
    enricher: LLMEnricher,
    change_summary: str = "",
) -> Optional[Opportunity]:
    """Create an opportunity from a signal"""
    # Score the signal
    score = await scorer.score(signal, domain)

    # Enrich with LLM (le résumé factuel reste la base du why_it_matters)
    enrichment = await enricher.enrich(signal, domain, change_summary=change_summary)
    why_it_matters = change_summary or enrichment.get("why_it_matters", "")

    # Create opportunity
    importance = resolve_signal_importance(
        signal.type, signal.payload_json if isinstance(signal.payload_json, dict) else None
    )
    opportunity = Opportunity(
        domain_id=signal.domain_id,
        company_name=domain.domain,  # Best effort - will be enriched
        country=None,  # Will be enriched
        signal_type=signal.type,
        importance=importance,
        proof_url=signal.proof_url,
        detected_at=signal.detected_at,
        score=score,
        why_it_matters=why_it_matters,
        suggested_approach=enrichment.get("suggested_approach", ""),
    )

    session.add(opportunity)
    await session.flush()

    # Index in Meilisearch
    await index_opportunity(opportunity)

    return opportunity


async def index_opportunity(opportunity: Opportunity):
    """Index opportunity in Meilisearch"""
    try:
        meili_client.index("opportunities").add_documents(
            [
                {
                    "id": str(opportunity.id),
                    "company_name": opportunity.company_name,
                    "domain": "",  # Will be filled from domain
                    "signal_type": opportunity.signal_type,
                    "country": opportunity.country or "",
                    "score": opportunity.score,
                    "why_it_matters": opportunity.why_it_matters,
                    "detected_at": opportunity.detected_at.isoformat(),
                }
            ]
        )
    except Exception as e:
        print(f"Error indexing opportunity: {e}")


async def process_snapshots():
    """Main processing loop"""
    started_at = time.perf_counter()
    worker_id = os.getenv("WORKER_ID", "").strip()
    worker_label = f"worker {worker_id}" if worker_id else "ce worker"
    orchestrator_ctx = get_orchestrator_context()
    idle_polls_to_finish = int(os.getenv("WORKER_IDLE_POLLS_TO_FINISH", "0") or "0")

    processed_count = 0
    signals_saved_total = 0
    opportunities_created_total = 0
    errors_count = 0
    batches_count = 0
    idle_polls = 0
    fatal_error: Optional[str] = None

    if orchestrator_ctx:
        print(
            f"Starting worker #{orchestrator_ctx['worker_index']} "
            f"(orchestrateur — fin après {idle_polls_to_finish} tour(s) vide)..."
        )
    else:
        print(f"Starting worker{f' ({worker_id})' if worker_id else ''}...")

    while True:
        try:
            async with AsyncSessionLocal() as session:
                snapshots = await get_pending_snapshots(
                    session, limit=config.WORKER_BATCH_SIZE
                )

                if not snapshots:
                    idle_polls += 1
                    print(
                        f"Aucun snapshot en attente — "
                        f"{processed_count} déjà traité(s) par {worker_label} — "
                        f"nouvelle tentative dans 15s..."
                    )
                    if (
                        orchestrator_ctx
                        and idle_polls_to_finish > 0
                        and idle_polls >= idle_polls_to_finish
                    ):
                        print(
                            f"✅ {worker_label} terminé — "
                            f"plus de snapshots à traiter."
                        )
                        break
                    if not orchestrator_ctx:
                        await asyncio.sleep(15)
                        continue
                    await asyncio.sleep(15)
                    continue

                idle_polls = 0
                batches_count += 1
                print(
                    f"Processing {len(snapshots)} snapshots (batch size target: {config.WORKER_BATCH_SIZE})..."
                )

                for snapshot in snapshots:
                    snapshot_id = snapshot.id
                    batch_signals_saved = 0
                    batch_opportunities_created = 0
                    try:
                        # Check if content has changed compared to last snapshot
                        content_changed, is_first_snapshot, previous_snapshot = (
                            await has_content_changed(snapshot, session)
                        )

                        if is_first_snapshot:
                            # First snapshot for this URL - mark as processed but don't create signals
                            # We need a baseline before we can detect real changes
                            print(
                                f"  [Snapshot {snapshot.id}] First snapshot for this URL (hash: {snapshot.hash[:8]}...), establishing baseline - no signals created"
                            )
                            meta = dict(snapshot.extracted_json or {})
                            meta.update(
                                {
                                    "processed": True,
                                    "processed_at": _utc_now_iso(),
                                    "content_changed": False,
                                    "is_first_snapshot": True,
                                    "reason": "first_snapshot_baseline",
                                }
                            )
                            snapshot.extracted_json = meta
                            continue

                        if not content_changed:
                            # Content hasn't changed, mark as processed without creating signals
                            print(
                                f"  [Snapshot {snapshot.id}] Content unchanged (hash: {snapshot.hash[:8]}...), skipping signal detection"
                            )
                            meta = dict(snapshot.extracted_json or {})
                            meta.update(
                                {
                                    "processed": True,
                                    "processed_at": _utc_now_iso(),
                                    "content_changed": False,
                                    "reason": "hash_unchanged",
                                }
                            )
                            snapshot.extracted_json = meta
                            continue

                        # Analyze if the change is significant
                        t0 = time.perf_counter()
                        change_analyzer = ChangeAnalyzer()
                        change_analysis = change_analyzer.analyze(
                            previous_snapshot.html_text or "", snapshot.html_text or ""
                        )
                        analyze_ms = int((time.perf_counter() - t0) * 1000)

                        is_significant = change_analysis["is_significant"]
                        change_summary_global = _truncate_change_summary(
                            change_analysis.get("added_text")
                            or change_analysis.get("removed_text")
                            or ""
                        )
                        if is_significant:
                            print(
                                f"  [Snapshot {snapshot.id}] Changement significatif "
                                f"(similarité {change_analysis['similarity']:.0%}, "
                                f"type {change_analysis['change_type']}, analyse {analyze_ms}ms)"
                                + (
                                    f" — {change_summary_global}"
                                    if change_summary_global
                                    else ""
                                )
                            )
                        elif not change_analysis.get("has_price_change"):
                            print(
                                f"  [Snapshot {snapshot.id}] Changement trop mineur "
                                f"(similarité {change_analysis['similarity']:.0%}) — "
                                f"aucun signal créé"
                            )
                            meta = dict(snapshot.extracted_json or {})
                            meta.update(
                                {
                                    "processed": True,
                                    "processed_at": _utc_now_iso(),
                                    "content_changed": True,
                                    "is_significant": False,
                                    "similarity": change_analysis["similarity"],
                                    "change_type": change_analysis["change_type"],
                                    "reason": "change_too_minor",
                                }
                            )
                            snapshot.extracted_json = meta
                            continue
                        else:
                            print(
                                f"  [Snapshot {snapshot.id}] Changement mineur "
                                f"mais variation de prix détectée "
                                f"(analyse {analyze_ms}ms)"
                            )

                        print(
                            f"  [Snapshot {snapshot.id}] Détection des signaux en cours..."
                        )
                        t1 = time.perf_counter()
                        signals = await detect_signals(
                            snapshot, previous_snapshot, change_analysis
                        )
                        detect_ms = int((time.perf_counter() - t1) * 1000)
                        print(
                            f"  [Snapshot {snapshot.id}] "
                            f"{len(signals)} signal(s) détecté(s) ({detect_ms}ms)"
                        )

                        # Get domain
                        result = await session.execute(
                            select(Domain).where(Domain.id == snapshot.domain_id)
                        )
                        domain = result.scalar_one_or_none()
                        if not domain:
                            meta = dict(snapshot.extracted_json or {})
                            meta.update(
                                {
                                    "processed": True,
                                    "processed_at": _utc_now_iso(),
                                    "content_changed": True,
                                    "error": "domain_not_found",
                                }
                            )
                            snapshot.extracted_json = meta
                            continue

                        scorer = Scorer()
                        enricher = LLMEnricher()

                        signals_saved = 0
                        opportunities_created = 0
                        batch_peak_importance = "weak"

                        for signal in signals:
                            change_summary = describe_signal_change(
                                signal, change_analysis
                            )
                            payload = dict(signal.payload_json or {})
                            payload["change_summary"] = change_summary
                            signal.payload_json = payload

                            importance = resolve_signal_importance(
                                signal.type,
                                payload if isinstance(payload, dict) else None,
                            )
                            if IMPORTANCE_RANK.get(importance, 0) > IMPORTANCE_RANK.get(
                                batch_peak_importance, 0
                            ):
                                batch_peak_importance = importance

                            print(
                                f"  [Snapshot {snapshot.id}] "
                                f"{format_signal_log_prefix(importance)} {signal.type} : "
                                f"{change_summary}"
                            )

                            # Deduplicate
                            if not await deduplicate_signal(signal, session):
                                print(
                                    f"  [Snapshot {snapshot.id}] "
                                    f"{format_signal_log_prefix(importance)} {signal.type} "
                                    f"ignoré (doublon récent)"
                                )
                                continue

                            # Save signal
                            signal.importance = importance
                            session.add(signal)
                            await session.flush()
                            signals_saved += 1
                            batch_signals_saved += 1

                            # Create opportunity
                            opportunity = await create_opportunity(
                                signal,
                                domain,
                                session,
                                scorer,
                                enricher,
                                change_summary=change_summary,
                            )
                            if opportunity:
                                opportunities_created += 1
                                batch_opportunities_created += 1

                                # Notify users about the new opportunity
                                try:
                                    opportunity_data = {
                                        "company_name": opportunity.company_name,
                                        "signal_type": opportunity.signal_type,
                                        "importance": opportunity.importance,
                                        "score": opportunity.score,
                                        "proof_url": opportunity.proof_url,
                                        "why_it_matters": opportunity.why_it_matters,
                                        "suggested_approach": opportunity.suggested_approach,
                                        "detected_at": (
                                            opportunity.detected_at.isoformat()
                                            if opportunity.detected_at
                                            else None
                                        ),
                                    }
                                    await notify_opportunity_created(
                                        opportunity_id=str(opportunity.id),
                                        opportunity_data=opportunity_data,
                                        domain_id=str(domain.id),
                                        org_id=(
                                            str(domain.org_id)
                                            if domain.org_id
                                            else None
                                        ),
                                    )
                                except Exception as e:
                                    print(
                                        f"  Warning: Failed to send notification for opportunity {opportunity.id}: {e}"
                                    )
                                    # Don't fail the whole process if notification fails

                        # Mark snapshot as processed (enrich existing metadata au lieu d'écraser)
                        meta = dict(snapshot.extracted_json or {})
                        meta.update(
                            {
                                "processed": True,
                                "processed_at": _utc_now_iso(),
                                "content_changed": True,
                                "is_significant": is_significant,
                                "similarity": change_analysis["similarity"],
                                "change_type": change_analysis["change_type"],
                                "added_text_length": change_analysis[
                                    "added_text_length"
                                ],
                                "removed_text_length": change_analysis[
                                    "removed_text_length"
                                ],
                                "signals_detected": len(signals),
                                "signals_saved": signals_saved,
                                "opportunities_created": opportunities_created,
                            }
                        )
                        snapshot.extracted_json = meta

                        if opportunities_created > 0:
                            print(
                                f"  [Snapshot {snapshot.id}] "
                                f"{signal_log_icon(batch_peak_importance)} Created "
                                f"{opportunities_created} opportunity/ies from "
                                f"{signals_saved} signal(s)"
                            )
                        elif len(signals) == 0:
                            print(
                                f"  [Snapshot {snapshot.id}] Aucun signal métier — snapshot marqué traité"
                            )

                    except Exception as e:
                        print(f"Error processing snapshot {snapshot_id}: {e}")
                        errors_count += 1
                        await _mark_snapshot_error(snapshot_id, str(e))
                    finally:
                        processed_count += 1
                        signals_saved_total += batch_signals_saved
                        opportunities_created_total += batch_opportunities_created

                await session.commit()

        except Exception as e:
            print(f"Fatal error in worker: {e}")
            fatal_error = str(e)
            if orchestrator_ctx:
                break
            await asyncio.sleep(60)

    if orchestrator_ctx:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        stats = WorkerRunStats(
            worker_index=orchestrator_ctx["worker_index"],
            status="error" if fatal_error else "completed",
            snapshots_processed=processed_count,
            signals_saved=signals_saved_total,
            opportunities_created=opportunities_created_total,
            errors=errors_count,
            batches=batches_count,
            duration_ms=duration_ms,
            finished_at=_utc_now_iso(),
            error_message=fatal_error,
        )
        write_worker_stats(
            orchestrator_ctx["stats_dir"],
            orchestrator_ctx["worker_index"],
            stats,
        )
        print(
            f"📄 Stats worker #{orchestrator_ctx['worker_index']} : "
            f"{processed_count} snapshot(s), "
            f"{opportunities_created_total} opportunité(s)"
        )


if __name__ == "__main__":
    asyncio.run(process_snapshots())
