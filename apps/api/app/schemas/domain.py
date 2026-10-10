"""
Domain schemas
"""
from datetime import datetime
from typing import Optional, Union, List
from pydantic import BaseModel, field_validator
import uuid


class DomainCreate(BaseModel):
    """Schema for domain creation"""

    domain: str
    org_id: Optional[uuid.UUID] = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate and normalize domain"""
        domain = v.strip().lower()
        # Remove protocol if present
        if "://" in domain:
            domain = domain.split("://")[1]
        # Remove trailing slash
        domain = domain.rstrip("/")
        # Remove www. prefix for normalization
        if domain.startswith("www."):
            domain = domain[4:]
        return domain


class DomainResponse(BaseModel):
    """Schema for domain response"""

    id: uuid.UUID
    domain: str
    org_id: Optional[uuid.UUID] = None
    status: str
    last_crawled_at: Optional[datetime] = None
    quarantine_until: Optional[datetime] = None
    error_count: int
    last_error: Optional[str] = None
    working_paths: Optional[List[str]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DomainUpdate(BaseModel):
    """Schema for domain update"""

    status: Optional[str] = None
    last_crawled_at: Optional[datetime] = None
    quarantine_until: Optional[datetime] = None
    error_count: Optional[int] = None
    last_error: Optional[str] = None
    working_paths: Optional[List[str]] = None

    @field_validator("last_crawled_at", "quarantine_until", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        """Parse datetime from string if needed"""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                # Handle ISO format with Z (UTC) - Python's fromisoformat doesn't handle Z
                v_clean = v.strip()
                if v_clean.endswith("Z") or v_clean.endswith("z"):
                    v_clean = v_clean[:-1] + "+00:00"
                # Try parsing ISO format
                parsed = datetime.fromisoformat(v_clean)
                return parsed
            except (ValueError, AttributeError) as e:
                # If parsing fails, raise a clear error
                raise ValueError(f"Invalid datetime format: {v}. Expected ISO format (e.g., '2026-02-05T22:03:19.492Z')") from e
        # If it's not a string or datetime, let Pydantic handle the validation
        return v


class DomainImportResponse(BaseModel):
    """Schema for CSV import response"""

    imported: int
    skipped: int
    errors: list[str]


class DomainCountResponse(BaseModel):
    """Schema for domain count (scraper orchestration)"""

    total: int
    active: int
