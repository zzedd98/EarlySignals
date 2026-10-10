"""Signal model"""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON

from app.models.base import BaseModel


class Signal(BaseModel):
    """Signal model"""

    __tablename__ = "signals"

    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False)
    type = Column(String(50), nullable=False, comment="jobs, pricing_change, tool_added, new_site, new_product, partnership, expansion, funding, page_redesign, recent_activity, minor_activity")
    importance = Column(
        String(10),
        nullable=False,
        default="strong",
        server_default="strong",
        comment="weak, medium, strong",
    )
    proof_url = Column(String(500), nullable=False)
    detected_at = Column(DateTime, nullable=False)
    payload_json = Column(JSON, nullable=True)
