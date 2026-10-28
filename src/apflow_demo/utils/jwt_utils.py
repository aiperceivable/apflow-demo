"""JWT generation and verification for demo sessions."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from apflow_demo.config.settings import settings


def generate_demo_jwt_token(user_id: str, expires_in_days: int = 365) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "demo": True, "iat": now, "exp": now + timedelta(days=expires_in_days)},
        settings.apflow_jwt_secret_key,
        algorithm=settings.apflow_jwt_algorithm,
    )


def verify_token(token: str, secret: str, algorithm: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except (jwt.PyJWTError, TypeError, ValueError):
        return None


def verify_demo_jwt_token(token: str) -> Optional[dict[str, Any]]:
    return verify_token(token, settings.apflow_jwt_secret_key, settings.apflow_jwt_algorithm)


def get_user_id_from_token(token: str) -> Optional[str]:
    payload = verify_demo_jwt_token(token)
    return payload.get("sub") if payload else None
