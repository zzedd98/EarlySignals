"""
Main API router
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, organizations, domains, snapshots, opportunities, notifications

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(domains.router, prefix="/domains", tags=["domains"])
api_router.include_router(snapshots.router, prefix="/snapshots", tags=["snapshots"])
api_router.include_router(opportunities.router, prefix="/opportunities", tags=["opportunities"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])