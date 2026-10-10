"""
Organization schemas
"""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel
import uuid


class OrganizationCreate(BaseModel):
    """Schema for organization creation"""

    name: str
    profile: Optional[str] = None
    countries: Optional[List[str]] = None
    notification_settings: Optional[Dict] = None


class OrganizationUpdate(BaseModel):
    """Schema for organization update"""

    name: Optional[str] = None
    profile: Optional[str] = None
    countries: Optional[List[str]] = None
    notification_settings: Optional[Dict] = None


class OrganizationResponse(BaseModel):
    """Schema for organization response"""

    id: uuid.UUID
    name: str
    profile: Optional[str] = None
    countries: Optional[List[str]] = None
    notification_settings: Optional[Dict] = None
    created_at: datetime

    class Config:
        from_attributes = True
