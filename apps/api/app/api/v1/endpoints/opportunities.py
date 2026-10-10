"""Opportunities endpoints"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.signal_importance import is_valid_importance
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.opportunity import OpportunityResponse, OpportunityUpdate

router = APIRouter()


@router.get("/", response_model=List[OpportunityResponse])
async def list_opportunities(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    score_min: Optional[int] = Query(None, ge=0, le=100),
    signal_type: Optional[str] = None,
    importance: Optional[str] = Query(
        None, description="Filtrer par niveau : weak, medium, strong"
    ),
    country: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List opportunities with filters"""
    if importance is not None and not is_valid_importance(importance):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="importance doit être weak, medium ou strong",
        )

    query = select(Opportunity)

    # Filter by user's org domains
    # TODO: Join with domains to filter by org_id

    if score_min is not None:
        query = query.where(Opportunity.score >= score_min)

    if signal_type:
        query = query.where(Opportunity.signal_type == signal_type)

    if importance:
        query = query.where(Opportunity.importance == importance)

    if country:
        query = query.where(Opportunity.country == country)

    query = query.offset(skip).limit(limit).order_by(Opportunity.score.desc(), Opportunity.detected_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get opportunity by ID"""
    result = await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    opportunity = result.scalar_one_or_none()
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    opportunity_id: str,
    update_data: OpportunityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update opportunity (e.g., favorite, to_contact)"""
    result = await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    opportunity = result.scalar_one_or_none()
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    if update_data.status_flags_json:
        current_flags = opportunity.status_flags_json or {}
        current_flags.update(update_data.status_flags_json)
        opportunity.status_flags_json = current_flags

    await db.commit()
    await db.refresh(opportunity)
    return opportunity
