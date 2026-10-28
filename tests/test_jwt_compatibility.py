from datetime import datetime, timedelta, timezone

import jwt


def test_demo_tokens_are_signed_and_verified(monkeypatch):
    from apflow_demo.config.settings import settings
    from apflow_demo.utils.jwt_utils import generate_demo_jwt_token, verify_demo_jwt_token

    monkeypatch.setattr(settings, "apflow_jwt_secret_key", "test-secret-key-with-at-least-32-bytes")
    token = generate_demo_jwt_token("user-123")
    assert verify_demo_jwt_token(token)["sub"] == "user-123"
    assert verify_demo_jwt_token(token + "invalid") is None


def test_expired_token_is_rejected(monkeypatch):
    from apflow_demo.config.settings import settings
    from apflow_demo.utils.jwt_utils import verify_demo_jwt_token

    monkeypatch.setattr(settings, "apflow_jwt_secret_key", "test-secret-key-with-at-least-32-bytes")
    token = jwt.encode(
        {"sub": "user-123", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        settings.apflow_jwt_secret_key,
        algorithm=settings.apflow_jwt_algorithm,
    )
    assert verify_demo_jwt_token(token) is None
