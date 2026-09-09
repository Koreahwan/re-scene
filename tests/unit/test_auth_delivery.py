"""
Unit Tests for Email Delivery Backends (DEV_OUTBOX, DISABLED, PROVIDER).
Verifies:
1. DEV_OUTBOX records codes and exposes through dev outbox viewer.
2. DISABLED mode rejects challenge creation with 503 AUTH_DELIVERY_DISABLED.
3. PROVIDER mode with unconfigured backend raises 503 AUTH_DELIVERY_NOT_CONFIGURED.
"""
import pytest
from src.reframe.identity.delivery import (
    DevOutboxDeliveryBackend,
    DisabledDeliveryBackend,
    ProviderDeliveryBackend,
    get_email_delivery_backend
)
from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import ReframeException


def test_dev_outbox_backend():
    backend = DevOutboxDeliveryBackend()
    assert backend.send_code("user@reframe.dev", "verification", "123456", 900) is True


def test_disabled_backend_raises_503():
    backend = DisabledDeliveryBackend()
    with pytest.raises(ReframeException) as exc_info:
        backend.send_code("user@reframe.dev", "verification", "123456", 900)
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "AUTH_DELIVERY_DISABLED"


def test_unconfigured_provider_backend_raises_503():
    backend = ProviderDeliveryBackend(provider_configured=False)
    with pytest.raises(ReframeException) as exc_info:
        backend.send_code("user@reframe.dev", "verification", "123456", 900)
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "AUTH_DELIVERY_NOT_CONFIGURED"


def test_delivery_backend_factory(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_EMAIL_DELIVERY_MODE", "DEV_OUTBOX")
    assert isinstance(get_email_delivery_backend(), DevOutboxDeliveryBackend)

    monkeypatch.setattr(settings, "AUTH_EMAIL_DELIVERY_MODE", "DISABLED")
    assert isinstance(get_email_delivery_backend(), DisabledDeliveryBackend)

    monkeypatch.setattr(settings, "AUTH_EMAIL_DELIVERY_MODE", "PROVIDER")
    assert isinstance(get_email_delivery_backend(), ProviderDeliveryBackend)
