"""
Script simple pour créer un utilisateur admin
Usage: python scripts/create_admin_simple.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.models.organization import Organization


async def create_admin():
    """Create admin user"""
    engine = create_async_engine(
        settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    )
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    email = "admin@example.com"
    password = "admin123456"

    async with AsyncSessionLocal() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            print(f"[OK] User {email} exists")
            # Update to admin
            user.role = UserRole.ADMIN
            # Update password hash
            user.password_hash = get_password_hash(password)
            print(f"[OK] Updated user {email} to ADMIN with new password")
        else:
            # Get or create organization
            result = await session.execute(
                select(Organization).where(Organization.name == "Admin Organization")
            )
            org = result.scalar_one_or_none()
            
            if not org:
                org = Organization(name="Admin Organization")
                session.add(org)
                await session.flush()

            # Create admin user
            admin_user = User(
                email=email,
                password_hash=get_password_hash(password),
                role=UserRole.ADMIN,
                org_id=org.id,
            )
            session.add(admin_user)
            print(f"[OK] Created admin user {email}")

        await session.commit()
        print(f"[OK] Admin user ready!")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Role: admin")


if __name__ == "__main__":
    asyncio.run(create_admin())
