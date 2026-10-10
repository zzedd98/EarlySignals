"""
Notification model
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Notification(BaseModel):
    """Notification model"""

    __tablename__ = "notifications"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    opportunity_id = Column(UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=True)
    type = Column(
        String(50),
        nullable=False,
        comment="email, in_app, slack",
    )
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, nullable=True, comment="Additional metadata (email sent, etc.)")

    # Relationships
    # user = relationship("User", back_populates="notifications")
    # opportunity = relationship("Opportunity", back_populates="notifications")
