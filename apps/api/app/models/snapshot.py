"""
Domain snapshot model
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class DomainSnapshot(BaseModel):
    """Domain snapshot model"""

    __tablename__ = "domain_snapshots"

    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False)
    url = Column(String(500), nullable=False)
    fetched_at = Column(DateTime, nullable=False)
    status_code = Column(Integer, nullable=False)
    hash = Column(String(64), nullable=False, index=True)
    html_storage_ref = Column(
        String(500),
        nullable=True,
        comment="Path to stored HTML file or reference",
    )
    html_text = Column(Text, nullable=True, comment="HTML content (compressed or full)")
    extracted_json = Column(JSON, nullable=True)

    # Relationships
    domain = relationship("Domain", back_populates="snapshots")
