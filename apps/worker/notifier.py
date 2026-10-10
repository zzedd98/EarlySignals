"""
Notification service for worker - sends notifications via API
"""
import httpx
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# API configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")
API_EMAIL = os.getenv("API_EMAIL", "admin@example.com")
API_PASSWORD = os.getenv("API_PASSWORD", "admin123")

# Cache for auth token
_auth_token: Optional[str] = None


async def get_auth_token() -> Optional[str]:
    """Get or refresh authentication token"""
    global _auth_token
    
    if _auth_token:
        return _auth_token
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_URL}/api/v1/auth/login",
                json={"email": API_EMAIL, "password": API_PASSWORD},
            )
            if response.status_code == 200:
                _auth_token = response.json().get("access_token")
                return _auth_token
            else:
                logger.error(f"Failed to authenticate: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error authenticating: {e}")
        return None


async def notify_opportunity_created(
    opportunity_id: str,
    opportunity_data: Dict[str, Any],
    domain_id: str,
    org_id: Optional[str] = None,
) -> bool:
    """
    Notify users about a new opportunity.
    Creates notifications in the database and sends emails if configured.
    
    Args:
        opportunity_id: UUID of the opportunity
        opportunity_data: Dict with opportunity fields (company_name, signal_type, score, etc.)
        domain_id: UUID of the domain
        org_id: Optional org_id to filter which users to notify
    
    Returns:
        True if notifications were sent successfully
    """
    try:
        token = await get_auth_token()
        if not token:
            logger.warning("Cannot notify: authentication failed")
            return False
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Call internal notification endpoint
            response = await client.post(
                f"{API_URL}/api/v1/notifications/opportunity",
                json={
                    "opportunity_id": opportunity_id,
                    "opportunity_data": opportunity_data,
                    "domain_id": domain_id,
                    "org_id": org_id,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            
            if response.status_code in (200, 201):
                logger.info(f"Notifications sent for opportunity {opportunity_id}")
                return True
            else:
                logger.error(f"Failed to send notifications: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Error sending notifications: {e}")
        return False
