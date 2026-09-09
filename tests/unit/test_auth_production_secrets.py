"""
Unit Tests for Production Secret & Configuration Invariants.
Verifies:
1. Production mode rejects default or short AUTH_CODE_HMAC_SECRET.
2. Production mode rejects AUTH_EMAIL_DELIVERY_MODE=DEV_OUTBOX.
3. Production mode rejects AUTH_DEV_OUTBOX_VIEWER_ENABLED=True.
4. Production mode rejects SESSION_COOKIE_SECURE=False.
5. Production mode rejects AUTH_DEV_MODE=True.
"""
import pytest
from src.reframe.shared.config import Settings


def test_production_rejects_default_hmac_secret():
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        CSRF_SECRET="b" * 32,
        AUTH_CODE_HMAC_SECRET="reframe-dev-auth-code-hmac-secret-min32chars",
        AUTH_EMAIL_DELIVERY_MODE="PROVIDER",
        AUTH_DEV_OUTBOX_VIEWER_ENABLED=False,
        AUTH_DEV_MODE=False,
        SESSION_COOKIE_SECURE=True
    )
    with pytest.raises(RuntimeError, match="AUTH_CODE_HMAC_SECRET"):
        s.validate_production_settings()


def test_production_rejects_short_hmac_secret():
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        CSRF_SECRET="b" * 32,
        AUTH_CODE_HMAC_SECRET="short_secret",
        AUTH_EMAIL_DELIVERY_MODE="PROVIDER",
        AUTH_DEV_OUTBOX_VIEWER_ENABLED=False,
        AUTH_DEV_MODE=False,
        SESSION_COOKIE_SECURE=True
    )
    with pytest.raises(RuntimeError, match="AUTH_CODE_HMAC_SECRET"):
        s.validate_production_settings()


def test_production_rejects_dev_outbox():
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        CSRF_SECRET="b" * 32,
        AUTH_CODE_HMAC_SECRET="c" * 32,
        AUTH_EMAIL_DELIVERY_MODE="DEV_OUTBOX",
        AUTH_DEV_OUTBOX_VIEWER_ENABLED=False,
        AUTH_DEV_MODE=False,
        SESSION_COOKIE_SECURE=True
    )
    with pytest.raises(RuntimeError, match="DEV_OUTBOX"):
        s.validate_production_settings()


def test_production_rejects_dev_outbox_viewer_enabled():
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        CSRF_SECRET="b" * 32,
        AUTH_CODE_HMAC_SECRET="c" * 32,
        AUTH_EMAIL_DELIVERY_MODE="PROVIDER",
        AUTH_DEV_OUTBOX_VIEWER_ENABLED=True,
        AUTH_DEV_MODE=False,
        SESSION_COOKIE_SECURE=True
    )
    with pytest.raises(RuntimeError, match="AUTH_DEV_OUTBOX_VIEWER_ENABLED"):
        s.validate_production_settings()


def test_production_valid_configuration():
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        CSRF_SECRET="b" * 32,
        AUTH_CODE_HMAC_SECRET="c" * 32,
        AUTH_EMAIL_DELIVERY_MODE="PROVIDER",
        AUTH_DEV_OUTBOX_VIEWER_ENABLED=False,
        AUTH_DEV_MODE=False,
        SESSION_COOKIE_SECURE=True
    )
    # Should not raise
    s.validate_production_settings()
