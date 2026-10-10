"""
Domain management endpoints (Admin)
"""
import csv
import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.domain import Domain
from app.models.user import User, UserRole
from app.models.snapshot import DomainSnapshot
from app.models.opportunity import Opportunity
from app.schemas.domain import (
    DomainCreate,
    DomainResponse,
    DomainUpdate,
    DomainImportResponse,
    DomainCountResponse,
)

router = APIRouter()


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.post("/", response_model=DomainResponse, status_code=status.HTTP_201_CREATED)
async def create_domain(
    domain_data: DomainCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new domain"""
    # Check if domain already exists
    result = await db.execute(select(Domain).where(Domain.domain == domain_data.domain))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Domain already exists",
        )

    # Set org_id if not provided (use current user's org)
    org_id = domain_data.org_id or current_user.org_id

    domain = Domain(domain=domain_data.domain, org_id=org_id)
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


@router.get("/", response_model=List[DomainResponse])
async def list_domains(
    skip: int = 0,
    limit: int = 100,
    org_id: str = None,
    status_filter: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List domains (admin sees all, users see their org's domains)"""
    query = select(Domain)

    # Filter by org if not admin
    if current_user.role != UserRole.ADMIN:
        query = query.where(Domain.org_id == current_user.org_id)
    elif org_id:
        query = query.where(Domain.org_id == org_id)

    # Filter by status
    if status_filter:
        query = query.where(Domain.status == status_filter)

    # Ordre stable pour la pagination multi-workers (skip/limit)
    query = query.order_by(Domain.created_at.asc(), Domain.domain.asc()).offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/count", response_model=DomainCountResponse)
async def count_domains(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Nombre de domaines (admin = tous, user = org). Utilisé par le scraper multi-workers."""
    org_filter = []
    if current_user.role != UserRole.ADMIN:
        org_filter.append(Domain.org_id == current_user.org_id)

    total_q = select(func.count()).select_from(Domain)
    for clause in org_filter:
        total_q = total_q.where(clause)
    total = (await db.execute(total_q)).scalar_one()

    active_q = (
        select(func.count())
        .select_from(Domain)
        .where(Domain.status == "active", *org_filter)
    )
    active = (await db.execute(active_q)).scalar_one()
    return DomainCountResponse(total=total, active=active)


@router.get("/{domain_id}", response_model=DomainResponse)
async def get_domain(
    domain_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get domain by ID"""
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found",
        )

    # Check access
    if current_user.role != UserRole.ADMIN and domain.org_id != current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return domain


@router.patch("/{domain_id}", response_model=DomainResponse)
async def update_domain(
    domain_id: str,
    domain_data: DomainUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a domain"""
    import logging
    import traceback
    
    logger = logging.getLogger(__name__)
    
    try:
        result = await db.execute(select(Domain).where(Domain.id == domain_id))
        domain = result.scalar_one_or_none()
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found",
            )

        # Check access
        if current_user.role != UserRole.ADMIN and domain.org_id != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Update fields
        try:
            if domain_data.status is not None:
                domain.status = domain_data.status
            if domain_data.last_crawled_at is not None:
                # Ensure it's a datetime object and convert to naive (no timezone)
                dt = domain_data.last_crawled_at
                if isinstance(dt, str):
                    from datetime import datetime
                    # Parse ISO format with Z
                    dt_str = dt.strip()
                    if dt_str.endswith("Z") or dt_str.endswith("z"):
                        dt_str = dt_str[:-1] + "+00:00"
                    dt = datetime.fromisoformat(dt_str)
                # Convert timezone-aware datetime to naive (remove timezone info)
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                domain.last_crawled_at = dt
            if domain_data.quarantine_until is not None:
                dt = domain_data.quarantine_until
                if isinstance(dt, str):
                    from datetime import datetime
                    dt_str = dt.strip()
                    if dt_str.endswith("Z") or dt_str.endswith("z"):
                        dt_str = dt_str[:-1] + "+00:00"
                    dt = datetime.fromisoformat(dt_str)
                # Convert timezone-aware datetime to naive (remove timezone info)
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                domain.quarantine_until = dt
            if domain_data.error_count is not None:
                domain.error_count = domain_data.error_count
            if domain_data.last_error is not None:
                domain.last_error = domain_data.last_error
            if domain_data.working_paths is not None:
                domain.working_paths = domain_data.working_paths

            await db.commit()
            await db.refresh(domain)
            return domain
        except ValueError as ve:
            logger.error(f"ValueError updating domain {domain_id}: {str(ve)}")
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date format: {str(ve)}",
            )
        except Exception as e:
            logger.error(f"Error updating domain {domain_id}: {str(e)}")
            logger.error(traceback.format_exc())
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating domain: {str(e)}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in update_domain: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(
    domain_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a domain (admin only)"""
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found",
        )

    # Delete related snapshots first
    snapshots_result = await db.execute(
        select(DomainSnapshot).where(DomainSnapshot.domain_id == domain_id)
    )
    snapshots = snapshots_result.scalars().all()
    for snapshot in snapshots:
        await db.delete(snapshot)

    # Delete related opportunities
    opportunities_result = await db.execute(
        select(Opportunity).where(Opportunity.domain_id == domain_id)
    )
    opportunities = opportunities_result.scalars().all()
    for opportunity in opportunities:
        await db.delete(opportunity)

    # Now delete the domain
    await db.delete(domain)
    await db.commit()
    return


@router.post("/import", response_model=DomainImportResponse)
async def import_domains_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Import domains from CSV file (admin only)"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV",
        )

    content = await file.read()
    csv_content = io.StringIO(content.decode("utf-8"))
    reader = csv.DictReader(csv_content)

    imported = 0
    skipped = 0
    errors: List[str] = []

    for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
        try:
            # Expect column "domain" or first column
            domain_str = row.get("domain") or list(row.values())[0] if row else None
            if not domain_str:
                skipped += 1
                errors.append(f"Row {row_num}: Empty domain")
                continue

            # Normalize domain
            domain_str = domain_str.strip().lower()
            if "://" in domain_str:
                domain_str = domain_str.split("://")[1]
            domain_str = domain_str.rstrip("/")
            if domain_str.startswith("www."):
                domain_str = domain_str[4:]

            # Check if exists
            result = await db.execute(
                select(Domain).where(Domain.domain == domain_str)
            )
            existing = result.scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            # Optional: working paths provided in CSV (pipe-separated URLs)
            working_paths_raw = row.get("working_paths") if row else None
            working_paths: list[str] | None = None
            if working_paths_raw:
                parts = [p.strip() for p in str(working_paths_raw).split("|") if p.strip()]
                if parts:
                    working_paths = parts

            # Create domain
            domain = Domain(domain=domain_str, org_id=None)  # Global pool
            if working_paths is not None:
                domain.working_paths = working_paths
            db.add(domain)
            imported += 1

        except Exception as e:
            skipped += 1
            errors.append(f"Row {row_num}: {str(e)}")

    await db.commit()

    return DomainImportResponse(imported=imported, skipped=skipped, errors=errors)
