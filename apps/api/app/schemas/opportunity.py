"""Opportunity schemas"""
from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel
import uuid


class OpportunityResponse(BaseModel):
    """Schema for opportunity response"""

    id: uuid.UUID
    domain_id: uuid.UUID
    company_name: str
    country: Optional[str] = None
    signal_type: str
    importance: str
    proof_url: str
    detected_at: datetime
    score: int
    why_it_matters: Optional[str] = None
    suggested_approach: Optional[str] = None
    status_flags_json: Optional[Dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OpportunityUpdate(BaseModel):
    """Schema for opportunity update"""

    status_flags_json: Optional[Dict] = None
