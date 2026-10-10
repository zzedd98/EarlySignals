"""
Script to create an admin user
Usage: python scripts/create_admin.py <email> <password>
"""
import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.models.organization import Organization


async def create_admin_user(email: str, password: str):
    """Create an admin user"""
    engine = create_async_engine(
        settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    )
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        # Check if user already exists
        result = await session.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            # Update to admin
            existing_user.role = UserRole.ADMIN
            print(f"✅ User {email} updated to ADMIN role")
        else:
            # Create organization
            org = Organization(name=f"Admin Organization for {email}")
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
            print(f"✅ Admin user {email} created successfully")

        await session.commit()
        print(f"✅ Admin user ready: {email}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/create_admin.py <email> <password>")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]

    asyncio.run(create_admin_user(email, password))
