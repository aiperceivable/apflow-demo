"""
Rate limiting middleware
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from apflow_demo.extensions.rate_limiter import RateLimiter
from apflow_demo.config.settings import settings
from apflow_demo.api.routes.user_routes import _check_admin_auth


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting"""
    
    async def dispatch(self, request: Request, call_next):
        """Check rate limit before processing request"""
        if request.method == "OPTIONS":
            return await call_next(request)

        if _check_admin_auth(request):
            return await call_next(request)

        # Skip rate limiting for certain paths
        skip_paths = ["/health", "/docs", "/openapi.json", "/redoc"]
        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)
        
        if not settings.rate_limit_enabled:
            return await call_next(request)
        
        # Extract user ID and IP
        user_id = None
        # Try to get user ID from JWT token or header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # In a real implementation, decode JWT to get user_id
            # For now, we'll use a simple approach
            pass
        
        # Get IP address
        ip_address = request.client.host if request.client else "unknown"
        # Check X-Forwarded-For header for proxied requests
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()
        
        # Check rate limit
        allowed, info = await RateLimiter.check_limit(
            user_id=user_id,
            ip_address=ip_address,
        )
        
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": -32000,
                        "message": "Rate limit exceeded",
                        "data": {
                            "reason": info.get("reason"),
                            "user_count": info.get("user_count"),
                            "user_limit": info.get("user_limit"),
                            "ip_count": info.get("ip_count"),
                            "ip_limit": info.get("ip_limit"),
                        },
                    }
                },
            )
        
        # Process request
        response = await call_next(request)
        
        # Increment counter after successful request
        if response.status_code < 400:
            await RateLimiter.record_request(
                user_id=user_id,
                ip_address=ip_address,
            )
        
        return response

