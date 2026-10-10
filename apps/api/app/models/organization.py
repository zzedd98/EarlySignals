"""
Organization model
"""
from sqlalchemy import Column, String, JSON, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.models.base import BaseModel


class Organization(BaseModel):
    """Organization model"""

    __tablename__ = "organizations"

    name = Column(String(255), nullable=False)
    profile = Column(
        String(50),
        nullable=True,
        comment="Profile type: dev_agency, growth_agency, recruitment, automation, premium_freelance, ecommerce",
    )
    countries = Column(
        JSON,
        nullable=True,
        default=list,
        comment="List of target countries (ISO codes)",
    )
    notification_settings = Column(
        JSON,
        nullable=True,
        default=dict,
        comment="Notification settings: email, slack_webhook, instant_threshold",
    )

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
