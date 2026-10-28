"""
Demo API server

Wraps apflow's A2A API with demo-specific authentication and user routes.

Uses apflow's registry and A2A adapter with demo-specific routes.
"""

import inspect
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, List
from starlette.routing import Route
from starlette.requests import Request
from apflow_demo.api.middleware.session_cookie import SessionCookieMiddleware
from apflow_demo.config.settings import settings
from apflow.logger import get_logger

logger = get_logger(__name__)


def _create_custom_routes() -> List[Route]:
    """
    Create custom routes for demo application
    
    Returns:
        List of Route objects
    """
    routes = []
    
    # Authentication routes
    from apflow_demo.api.routes.auth_routes import AuthRoutes
    auth_routes = AuthRoutes()
    
    async def auto_login_handler(request: Request):
        return await auth_routes.handle_auto_login(request)
    
    routes.append(Route("/auth/auto-login", auto_login_handler, methods=["GET"]))
    logger.info("Added auth route: /auth/auto-login")
    
    # User management routes
    from apflow_demo.api.routes.user_routes import UserRoutes
    user_routes = UserRoutes()
    
    async def list_users_handler(request: Request):
        limit = int(request.query_params.get("limit", 20))
        status = request.query_params.get("status")
        return await user_routes.handle_list_users(request, limit=limit, status=status)
    
    async def user_stats_handler(request: Request):
        period = request.query_params.get("period", "all")
        return await user_routes.handle_user_stats(request, period=period)
    
    routes.append(Route("/api/users/list", list_users_handler, methods=["GET"]))
    routes.append(Route("/api/users/stats", user_stats_handler, methods=["GET"]))
    logger.info("Added user routes: /api/users/list (GET), /api/users/stats (GET)")
    
    return routes


def _create_custom_middleware() -> List:
    """
    Create custom middleware for demo application
    
    Returns:
        List of middleware classes
    """
    middleware = []
    
    # Session cookie middleware (runs first, sets authorization cookie)
    # This enables browser fingerprinting + JWT token generation for user identification
    # Cookie: httponly=True, max_age=1 year, samesite=lax
    # JWT token is added to Authorization header for apflow's JWT middleware
    middleware.append(SessionCookieMiddleware)
    
    return middleware


@asynccontextmanager
async def _app_lifespan(app: Any) -> AsyncGenerator[None, None]:
    """Initialize apflow and its A2A transport for the lifetime of the server."""
    from apcore import Executor
    from apcore_a2a import async_serve
    from apcore_a2a.auth import JWTAuthenticator
    from apflow.app import create_app
    from apflow.bridge.protocol import PublicExecutor

    if os.getenv("RATE_LIMIT_ENABLED", "").lower() in ("1", "true", "yes"):
        logger.warning("RATE_LIMIT_ENABLED is obsolete; this service does not enforce request or task quotas")

    if not settings.apflow_jwt_secret_key:
        raise RuntimeError("A JWT secret is required for demo authentication")

    core = create_app(connection_string=settings.database_url)
    try:
        auth = JWTAuthenticator(
            settings.apflow_jwt_secret_key, algorithms=[settings.apflow_jwt_algorithm]
        )
        executor = PublicExecutor(Executor.from_registry(core.registry))
        a2a = await async_serve(
            executor,
            name="apflow-demo",
            url=settings.apflow_base_url or f"http://{settings.apflow_api_host}:{settings.apflow_api_port}",
            auth=auth,
            cors_origins=([origin.strip() for origin in settings.apflow_cors_origins.split(",")]
                          if settings.apflow_cors_origins else None),
        )
        app.state.a2a = a2a
        async with a2a.router.lifespan_context(a2a):
            yield
    finally:
        result = core.session.close()
        if inspect.isawaitable(result):
            await result


class _A2AProxy:
    """Forward requests to the A2A app initialized during startup."""

    def __init__(self, owner: Any) -> None:
        self.owner = owner

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self.owner.state.a2a(scope, receive, send)


def create_demo_app() -> Any:
    """Create the demo ASGI application using apflow's public A2A adapter."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Mount

    app = Starlette(
        routes=_create_custom_routes(),
        middleware=[Middleware(cls) for cls in _create_custom_middleware()],
        lifespan=_app_lifespan,
    )
    app.router.routes.append(Mount("/", app=_A2AProxy(app)))
    return app
