"""
User management routes for demo application

Provides API endpoints for querying user information.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse
from typing import Optional
from apflow_demo.services.user_service import user_tracking_service
from apflow_demo.utils.jwt_utils import verify_demo_jwt_token
from apflow.logger import get_logger

logger = get_logger(__name__)


def _check_admin_auth(request: Request) -> bool:
    """
    Check if request has valid admin authentication
    
    Checks Authorization header or cookie for admin JWT token.
    Supports both API server's JWT secret and CLI's JWT secret.
    
    If .env has no APFLOW_JWT_SECRET, allows admin tokens from CLI config.
    """
    from apflow.api.a2a.server import verify_token
    from pathlib import Path
    import yaml
    import os
    
    # Get token from Authorization header or cookie
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
    else:
        token = request.cookies.get("authorization")
    
    if not token:
        logger.debug("No token found in Authorization header or cookie")
        return False
    
    # Check if .env has APFLOW_JWT_SECRET set (not using default)
    from apflow_demo.config.settings import settings
    env_has_jwt_secret = bool(
        os.getenv("APFLOW_JWT_SECRET")
    )
    
    logger.debug(f"Checking admin auth: env_has_jwt_secret={env_has_jwt_secret}, token_prefix={token[:20] if token else None}...")
    
    # Try API server's JWT secret first (if configured)
    if env_has_jwt_secret:
        api_secret = settings.apflow_jwt_secret_key
        api_algorithm = settings.apflow_jwt_algorithm
        if api_secret:
            payload = verify_token(token, api_secret, api_algorithm)
            if payload and isinstance(payload.get("roles", []), list) and "admin" in payload.get("roles", []):
                logger.debug("Admin auth successful with API server JWT secret")
                return True
            else:
                logger.debug(f"Token verification with API secret failed: payload={payload}")
    
    # Always try CLI's JWT secret (from config.cli.yaml)
    # This is needed when CLI generates tokens with its own secret
    # Even if .env has APFLOW_JWT_SECRET, CLI tokens may use different secret
    try:
        # Try multiple possible locations for config.cli.yaml
        possible_paths = [
            Path.cwd() / ".data" / "config.cli.yaml",  # Project-specific
            Path.cwd() / "config.cli.yaml",  # Project root
            Path.home() / ".apflow" / "config.cli.yaml",  # User home
        ]
        
        config_path = None
        for path in possible_paths:
            if path.exists():
                config_path = path
                break
        
        if config_path:
            with open(config_path, "r") as f:
                cli_config = yaml.safe_load(f)
                if cli_config and "jwt_secret" in cli_config:
                    cli_secret = cli_config["jwt_secret"]
                    cli_algorithm = cli_config.get("jwt_algorithm", "HS256")
                    payload = verify_token(token, cli_secret, cli_algorithm)
                    if payload and isinstance(payload.get("roles", []), list) and "admin" in payload.get("roles", []):
                        logger.debug(f"Admin auth successful with CLI JWT secret from {config_path}")
                        return True
                    else:
                        logger.debug(f"Token verification with CLI secret failed: payload={payload}")
        else:
            logger.debug("config.cli.yaml not found in any standard location")
    except Exception as e:
        logger.warning(f"Failed to check CLI JWT secret: {e}", exc_info=True)
    
    logger.debug("Admin authentication failed - no valid admin token found")
    return False


class UserRoutes:
    """Routes for user management"""

    async def handle_list_users(
        self,
        request: Request,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> JSONResponse:
        """
        Handle user list request
        
        GET /api/users/list?limit=20&status=active
        
        Requires admin authentication via Bearer token or cookie.
        
        Returns:
            JSONResponse with list of users
        """
        # Check admin authentication
        if not _check_admin_auth(request):
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "unauthorized",
                    "message": "Admin authentication required",
                }
            )
        
        try:
            from sqlalchemy import select
            from sqlalchemy.sql import desc
            from apflow.core.storage import create_pooled_session
            from apflow_demo.storage.models import DemoUser
            from sqlalchemy.ext.asyncio import AsyncSession

            async def _list_users():
                async with create_pooled_session() as session:
                    stmt = select(DemoUser).order_by(desc(DemoUser.last_active_at)).limit(limit)
                    if status:
                        stmt = stmt.where(DemoUser.status == status)
                    
                    if isinstance(session, AsyncSession):
                        result = await session.execute(stmt)
                        return result.scalars().all()
                    else:
                        result = session.execute(stmt)
                        return result.scalars().all()

            users = await _list_users()
            
            users_data = []
            for user in users:
                users_data.append({
                    "user_id": user.user_id,
                    "username": user.username,
                    "status": user.status,
                    "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
                    "source": user.source,
                    "user_agent": user.user_agent,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                })
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "users": users_data,
                    "count": len(users_data),
                }
            )
            
        except Exception as e:
            logger.error(f"Error listing users: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "list_users_failed",
                    "message": f"Failed to list users: {str(e)}",
                }
            )

    async def handle_user_stats(
        self,
        request: Request,
        period: str = "all",
    ) -> JSONResponse:
        """
        Handle user statistics request
        
        GET /api/users/stats?period=day
        
        Requires admin authentication via Bearer token or cookie.
        
        Returns:
            JSONResponse with user statistics
        """
        # Check admin authentication
        if not _check_admin_auth(request):
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "unauthorized",
                    "message": "Admin authentication required",
                }
            )
        
        try:
            stats = await user_tracking_service.get_user_stats(period)
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    **stats,
                }
            )
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "stats_failed",
                    "message": f"Failed to get user statistics: {str(e)}",
                }
            )

