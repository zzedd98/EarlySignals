"""
Snapshot endpoints (internal - used by scraper)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from datetime import datetime
from typing import List, Optional
import uuid
import logging

from app.core.database import get_db
from app.core.text_sanitize import sanitize_pg_text
from app.core.dependencies import get_current_user
from app.models.snapshot import DomainSnapshot
from app.models.domain import Domain
from app.schemas.snapshot import SnapshotCreate, SnapshotResponse, SnapshotBulkCreate, SnapshotBulkResponse
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


async def _latest_hash_map_for_domains(
    db: AsyncSession,
    domain_ids: list[uuid.UUID],
) -> dict[tuple[uuid.UUID, str], str]:
    """Dernier hash par (domain_id, url) — sans charger le HTML."""
    if not domain_ids:
        return {}

    ranked = (
        select(
            DomainSnapshot.domain_id,
            DomainSnapshot.url,
            DomainSnapshot.hash,
            func.row_number()
            .over(
                partition_by=(DomainSnapshot.domain_id, DomainSnapshot.url),
                order_by=desc(DomainSnapshot.fetched_at),
            )
            .label("rn"),
        )
        .where(DomainSnapshot.domain_id.in_(domain_ids))
        .subquery()
    )
    result = await db.execute(
        select(ranked.c.domain_id, ranked.c.url, ranked.c.hash).where(ranked.c.rn == 1)
    )
    return {(row.domain_id, row.url): row.hash for row in result.all()}


@router.post("/", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    snapshot_data: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new snapshot (internal API for scraper).

    Robustness / scalability:
    - Avoids storing duplicate snapshots when the latest snapshot for the same
      (domain_id, url) already has the same hash.
    - This prevents the database from filling up with exact duplicates when the
      scraper is run plusieurs fois d'affilée sur les mêmes pages.
    """
    # Check if the latest snapshot for this domain+url already has the same hash
    existing_result = await db.execute(
        select(DomainSnapshot)
        .where(DomainSnapshot.domain_id == snapshot_data.domain_id)
        .where(DomainSnapshot.url == snapshot_data.url)
        .order_by(desc(DomainSnapshot.fetched_at))
        .limit(1)
    )
    existing_snapshot = existing_result.scalar_one_or_none()

    if existing_snapshot and existing_snapshot.hash == snapshot_data.hash:
        # Exact duplicate: return the existing snapshot without creating a new row
        return existing_snapshot

    # Otherwise, create a fresh snapshot
    snapshot = DomainSnapshot(
        domain_id=snapshot_data.domain_id,
        url=snapshot_data.url,
        fetched_at=snapshot_data.fetched_at or datetime.utcnow(),
        status_code=snapshot_data.status_code,
        hash=snapshot_data.hash,
        html_text=sanitize_pg_text(snapshot_data.html),
        extracted_json=snapshot_data.extracted_json,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


def _snapshots_to_insert(
    bulk_data: SnapshotBulkCreate,
    existing_map: dict[tuple[uuid.UUID, str], str],
) -> tuple[list[DomainSnapshot], int]:
    new_snapshots: list[DomainSnapshot] = []
    skipped_count = 0

    for snapshot_data in bulk_data.snapshots:
        key = (snapshot_data.domain_id, snapshot_data.url)
        if existing_map.get(key) == snapshot_data.hash:
            skipped_count += 1
            continue

        snapshot = DomainSnapshot(
            domain_id=snapshot_data.domain_id,
            url=snapshot_data.url,
            fetched_at=snapshot_data.fetched_at or datetime.utcnow(),
            status_code=snapshot_data.status_code,
            hash=snapshot_data.hash,
            html_text=sanitize_pg_text(snapshot_data.html),
            extracted_json=snapshot_data.extracted_json,
        )
        new_snapshots.append(snapshot)
        # Même batch : éviter deux inserts identiques
        existing_map[key] = snapshot_data.hash

    return new_snapshots, skipped_count


@router.post("/bulk", response_model=SnapshotBulkResponse, status_code=status.HTTP_201_CREATED)
async def create_snapshots_bulk(
    bulk_data: SnapshotBulkCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create multiple snapshots in a single request.

    - Déduplication par (domain_id, url, hash) vs dernier snapshot connu
    - Insert par chunks pour limiter taille transaction / timeout
    - Réponse légère (compteurs uniquement, pas de HTML)
    """
    if not bulk_data.snapshots:
        return SnapshotBulkResponse(saved_count=0, skipped_count=0, failed_count=0)

    domain_ids = list({s.domain_id for s in bulk_data.snapshots})

    existing_map = await _latest_hash_map_for_domains(db, domain_ids)

    new_snapshots, skipped_count = _snapshots_to_insert(bulk_data, existing_map)
    if skipped_count:
        logger.info("Bulk snapshots: %d doublon(s) ignoré(s)", skipped_count)

    if not new_snapshots:
        return SnapshotBulkResponse(saved_count=0, skipped_count=skipped_count, failed_count=0)

    saved_count = 0
    failed_count = 0
    for snapshot in new_snapshots:
        try:
            async with db.begin_nested():
                db.add(snapshot)
                await db.flush()
            saved_count += 1
        except Exception as exc:
            failed_count += 1
            logger.warning(
                "Bulk snapshot skip domain_id=%s url=%s: %s",
                snapshot.domain_id,
                snapshot.url,
                exc,
            )

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Bulk snapshot commit failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk snapshot commit failed: {exc}",
        ) from exc

    if failed_count:
        logger.warning(
            "Bulk snapshots: %d saved, %d failed (others kept)",
            saved_count,
            failed_count,
        )

    return SnapshotBulkResponse(
        saved_count=saved_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
    )


@router.get("/", response_model=List[SnapshotResponse])
async def list_snapshots(
    domain_id: Optional[str] = Query(None, description="Filter by domain ID"),
    domain_ids: Optional[str] = Query(None, description="Comma-separated list of domain IDs (for scraper cache)"),
    limit: int = Query(50, ge=1, le=1000, description="Number of results"),
    skip: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List snapshots (admin only or for own domains).
    
    For scraper cache: use domain_ids=id1,id2,id3 to get latest snapshot per (domain_id, url).
    """
    query = select(DomainSnapshot)
    
    # Filter by single domain_id (legacy)
    if domain_id:
        query = query.where(DomainSnapshot.domain_id == domain_id)
    
    # Filter by multiple domain_ids (for scraper cache - efficient batch loading)
    if domain_ids:
        domain_id_list = [d.strip() for d in domain_ids.split(',') if d.strip()]
        if domain_id_list:
            query = query.where(DomainSnapshot.domain_id.in_(domain_id_list))
    
    # If not admin, only show snapshots from own domains
    if current_user.role.value != "admin":
        query = query.join(Domain).where(Domain.org_id == current_user.org_id)
    
    # Order by most recent first
    query = query.order_by(desc(DomainSnapshot.fetched_at)).limit(limit).offset(skip)
    
    result = await db.execute(query)
    snapshots = result.scalars().all()
    return snapshots


@router.get("/{snapshot_id}", response_model=SnapshotResponse)
async def get_snapshot(
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific snapshot"""
    result = await db.execute(
        select(DomainSnapshot).where(DomainSnapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found",
        )
    
    # Check access (admin or own domain)
    if current_user.role.value != "admin":
        result_domain = await db.execute(
            select(Domain).where(Domain.id == snapshot.domain_id)
        )
        domain = result_domain.scalar_one_or_none()
        if not domain or domain.org_id != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    
    return snapshot
