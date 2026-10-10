"""
Snapshot schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import uuid


class SnapshotCreate(BaseModel):
    """Schema for snapshot creation"""

    domain_id: uuid.UUID
    url: str
    fetched_at: Optional[datetime] = None
    status_code: int
    hash: str
    html: Optional[str] = None
    extracted_json: Optional[Dict[str, Any]] = None


class SnapshotBulkCreate(BaseModel):
    """Schema for bulk snapshot creation"""
    snapshots: List[SnapshotCreate]


class SnapshotBulkResponse(BaseModel):
    """Réponse légère — pas de HTML (évite timeout / 500 sur grosses réponses)."""

    saved_count: int
    skipped_count: int
    failed_count: int = 0


class SnapshotResponse(BaseModel):
    """Schema for snapshot response"""
    
    id: uuid.UUID
    domain_id: uuid.UUID
    url: str
    fetched_at: datetime
    status_code: int
    hash: str
    html_storage_ref: Optional[str] = None
    html_text: Optional[str] = None
    extracted_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
