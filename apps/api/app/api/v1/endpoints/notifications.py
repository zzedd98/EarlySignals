"""
Notification endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.notification import Notification
from app.models.user import User
from app.models.organization import Organization
from app.models.domain import Domain
from app.models.opportunity import Opportunity
from app.core.email import send_email, format_opportunity_email
from app.schemas.notification import NotificationResponse, NotificationCreate

router = APIRouter()


@router.post("/opportunity", status_code=status.HTTP_201_CREATED)
async def notify_opportunity_created_internal(
    opportunity_id: str = Body(...),
    opportunity_data: dict = Body(...),
    domain_id: str = Body(...),
    org_id: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # Internal API, admin only
):
    """
    Internal endpoint called by worker to create notifications for a new opportunity.
    Creates in-app notifications and sends emails based on user preferences.
    """
    # Get domain to find org_id if not provided
    if not org_id:
        domain_result = await db.execute(select(Domain).where(Domain.id == domain_id))
        domain = domain_result.scalar_one_or_none()
        if domain and domain.org_id:
            org_id = str(domain.org_id)
    
    # Get users to notify
    # If org_id is provided, notify users from that org
    # Otherwise, notify all users (for global pool domains)
    if org_id:
        org_result = await db.execute(select(Organization).where(Organization.id == org_id))
        org = org_result.scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Get users from this org
        users_result = await db.execute(select(User).where(User.org_id == org_id))
        users = users_result.scalars().all()
    else:
        # Global pool - notify all users (or you could skip this)
        users_result = await db.execute(select(User))
        users = users_result.scalars().all()
    
    notifications_created = 0
    emails_sent = 0
    
    for user in users:
        # Check notification settings
        org_result = await db.execute(select(Organization).where(Organization.id == user.org_id))
        org = org_result.scalar_one_or_none()
        
        if not org:
            continue
        
        notification_settings = org.notification_settings or {}
        email_enabled = notification_settings.get("email", True)
        instant_threshold = notification_settings.get("instant_threshold", 70)
        
        # Only notify if score meets threshold
        score = opportunity_data.get("score", 0)
        if score < instant_threshold:
            continue
        
        # Create in-app notification
        notification = Notification(
            user_id=user.id,
            opportunity_id=opportunity_id,
            type="in_app",
            title=f"Nouvelle opportunité : {opportunity_data.get('company_name', 'Unknown')}",
            message=f"Signal détecté : {opportunity_data.get('signal_type', 'unknown')} (Score: {score}/100)",
            read=False,
            metadata_json={"opportunity_data": opportunity_data},
        )
        db.add(notification)
        notifications_created += 1
        
        # Send email if enabled
        if email_enabled:
            domain_result = await db.execute(select(Domain).where(Domain.id == domain_id))
            domain = domain_result.scalar_one_or_none()
            domain_name = domain.domain if domain else "Unknown"
            
            subject, html_body = format_opportunity_email(opportunity_data, domain_name)
            
            if send_email(user.email, subject, html_body):
                emails_sent += 1
                
                # Create email notification record
                email_notification = Notification(
                    user_id=user.id,
                    opportunity_id=opportunity_id,
                    type="email",
                    title=subject,
                    message=html_body[:500],  # Truncate for storage
                    read=False,
                    metadata_json={"email_sent": True, "sent_at": datetime.utcnow().isoformat()},
                )
                db.add(email_notification)
    
    await db.commit()
    
    return {
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
        "users_notified": len(users),
    }


@router.get("/", response_model=List[NotificationResponse])
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notifications for current user"""
    query = select(Notification).where(Notification.user_id == current_user.id)
    
    if unread_only:
        query = query.where(Notification.read == False)
    
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a notification as read"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == current_user.id,
            )
        )
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.read = True
    notification.read_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(notification)
    
    return notification


@router.patch("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all notifications as read for current user"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read == False,
            )
        )
    )
    notifications = result.scalars().all()
    
    for notification in notifications:
        notification.read = True
        notification.read_at = datetime.utcnow()
    
    await db.commit()
    
    return {"marked_read": len(notifications)}


@router.get("/unread-count", status_code=status.HTTP_200_OK)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get count of unread notifications"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read == False,
            )
        )
    )
    count = len(result.scalars().all())
    
    return {"unread_count": count}
