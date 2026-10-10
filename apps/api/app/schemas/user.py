"""
User schemas
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_serializer
import uuid

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Schema for user creation"""

    email: EmailStr
    password: str
    org_id: Optional[uuid.UUID] = None


class UserLogin(BaseModel):
    """Schema for user login"""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response"""

    id: uuid.UUID
    email: str
    role: UserRole
    org_id: uuid.UUID
    created_at: datetime

    @field_serializer('role')
    def serialize_role(self, role: UserRole) -> str:
        """Serialize role enum as string"""
        return role.value if isinstance(role, UserRole) else str(role)

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema for JWT token"""

    access_token: str
    token_type: str = "bearer"
