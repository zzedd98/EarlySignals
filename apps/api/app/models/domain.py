"""
Domain model
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import BaseModel


class Domain(BaseModel):
    """Domain model"""

    __tablename__ = "domains"

    domain = Column(String(255), nullable=False, unique=True, index=True)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=True,
        comment="If null, domain is in global pool",
    )
    status = Column(
        String(50),
        default="active",
        nullable=False,
        comment="active, paused, quarantined",
    )
    last_crawled_at = Column(DateTime, nullable=True)
    quarantine_until = Column(DateTime, nullable=True)
    error_count = Column(
        Integer, default=0, nullable=False, comment="Consecutive error count"
    )
    last_error = Column(String(500), nullable=True)
    working_paths = Column(
        JSON,
        nullable=True,
        default=list,
        comment="List of URLs that have successfully returned relevant content for this domain (persistent, stored in database)",
    )

    # Relationships
    snapshots = relationship("DomainSnapshot", back_populates="domain")
