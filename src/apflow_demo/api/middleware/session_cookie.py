"""
Session cookie middleware with JWT token generation

Sets demo JWT token cookie on first request for persistent user identification.
Uses browser fingerprinting to generate stable user IDs, then creates JWT tokens
that are compatible with apflow's JWT middleware.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from apflow_demo.utils.user_identification import get_or_create_user_id
from apflow_demo.utils.jwt_utils import generate_demo_jwt_token, get_user_id_from_token
from apflow_demo.config.settings import settings
from apflow_demo.services.user_service import user_tracking_service
from apflow.logger import get_logger

logger = get_logger(__name__)


class SessionCookieMiddleware(BaseHTTPMiddleware):
    """
    Set demo JWT token cookie for persistent user identification
    
    This middleware:
    1. Generates user_id from browser fingerprint or reads from cookie
    2. Creates JWT token with user_id in 'sub' claim
    3. Stores JWT token in cookie (authorization)
    
    apflow's JWT middleware automatically reads from cookie, so no need to
    modify Authorization header.
    
    Cookie properties:
    - httponly=True: Prevents JavaScript access (security)
    - max_age=1 year: Persistent identification
    - samesite=lax: CSRF protection
    - secure: Set based on environment (HTTPS in production)
    """
    
    def __init__(self, app, secret_key: str = None):
        super().__init__(app)
        self.secret_key = secret_key
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and set JWT token cookie if needed
        
        Flow:
        1. Check if authorization cookie exists
        2. If not, generate user_id from browser fingerprint and create JWT token
        3. Store JWT token in cookie (apflow's JWT middleware reads from cookie automatically)
        
        This middleware processes ALL requests, including /auth/auto-login endpoint.
        When webapp calls /auth/auto-login on startup, this middleware will:
        - Generate user_id from browser fingerprint (if cookie doesn't exist)
        - Create JWT token with user_id
        - Set authorization cookie in response
        - Subsequent API requests will automatically include this cookie
        
        Note: No need to modify Authorization header - apflow now supports cookie-based auth.
        """
        # Check if JWT token exists in cookie
        jwt_token = request.cookies.get("authorization")
        user_id = None
        new_token_generated = False
        
        if jwt_token:
            # Extract user_id from existing token (for logging)
            user_id = get_user_id_from_token(jwt_token)
        else:
            # No token exists, generate new one from browser fingerprint
            # This creates a stable user_id based on browser characteristics
            from apflow_demo.utils.user_identification import generate_user_id_from_fingerprint
            user_id = generate_user_id_from_fingerprint(request.headers)
            jwt_token = generate_demo_jwt_token(user_id, expires_in_days=365)
            new_token_generated = True
            logger.debug(f"Generated new JWT token from fingerprint for user: {user_id[:20]}...")
        
        # Track user activity (async)
        # We don't necessarily need to await it if we don't want to block the request,
        # but for demo purposes it's safer to ensure the user exists.
        try:
            user_agent = request.headers.get("user-agent")
            await user_tracking_service.track_user_activity(user_id, source="web", user_agent=user_agent)
        except Exception as e:
            logger.error(f"Failed to track user activity: {e}")
        
        # The apcore A2A authenticator accepts bearer tokens, so forward the
        # session cookie when the client did not provide an Authorization header.
        if jwt_token and not request.headers.get("authorization"):
            request.scope["headers"] = [
                *request.scope["headers"],
                (b"authorization", f"Bearer {jwt_token}".encode("ascii")),
            ]
            if hasattr(request, "_headers"):
                del request._headers

        response = await call_next(request)
        
        # Set cookie if not already set or if new token was generated (persistent for 1 year)
        if (new_token_generated or "authorization" not in request.cookies) and jwt_token:
            # Determine secure flag based on environment
            # In production with HTTPS, set secure=True
            secure = settings.apflow_base_url and settings.apflow_base_url.startswith("https")
            
            response.set_cookie(
                key="authorization",
                value=jwt_token,
                max_age=365 * 24 * 60 * 60,  # 1 year (365 days)
                httponly=True,  # Prevent JavaScript access
                samesite="lax",  # CSRF protection
                secure=secure,  # HTTPS only in production
                path="/",  # Available for all paths
            )
            logger.debug(f"Set authorization cookie for user: {user_id[:20] if user_id else 'unknown'}... (httponly, 1 year)")
        
        return response

