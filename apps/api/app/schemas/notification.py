"""
Notification schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
import uuid


class NotificationResponse(BaseModel):
    """Schema for notification response"""
    
    id: uuid.UUID
    user_id: uuid.UUID
    opportunity_id: Optional[uuid.UUID] = None
    type: str
    title: str
    message: Optional[str] = None
    read: bool
    read_at: Optional[datetime] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    """Schema for notification creation"""
    
    user_id: uuid.UUID
    opportunity_id: Optional[uuid.UUID] = None
    type: str
    title: str
    message: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
