"""Opportunity model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSON

from app.models.base import BaseModel


class Opportunity(BaseModel):
    """Opportunity model"""

    __tablename__ = "opportunities"

    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False)
    company_name = Column(String(255), nullable=False)
    country = Column(String(2), nullable=True)
    signal_type = Column(String(50), nullable=False)
    importance = Column(
        String(10),
        nullable=False,
        default="strong",
        server_default="strong",
        comment="weak, medium, strong",
    )
    proof_url = Column(String(500), nullable=False)
    detected_at = Column(DateTime, nullable=False)
    score = Column(Integer, nullable=False)
    why_it_matters = Column(Text, nullable=True)
    suggested_approach = Column(Text, nullable=True)
    status_flags_json = Column(JSON, default=dict, nullable=True)
