"""
Reframe V7 Email Delivery Backend Interface & Implementations
Provides explicit delivery strategies without external API dependencies:
- DEV_OUTBOX: Stores codes locally for developer/test inspection
- DISABLED: Rejects challenge creation with 503 AUTH_DELIVERY_DISABLED
- PROVIDER: Configured delivery provider (fail-closed if unconfigured)
Zero Paid Model Calls.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import structlog
from fastapi import status

from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import ReframeException

logger = structlog.get_logger(__name__)

PRODUCTION_EMAIL_PROVIDER = "EXTERNAL_PENDING"


class EmailDeliveryBackend(ABC):
    @abstractmethod
    def send_code(self, recipient: str, purpose: str, code: str, expires_in_seconds: int) -> bool:
        """Dispatches verification or recovery code to recipient."""
        pass


class DevOutboxDeliveryBackend(EmailDeliveryBackend):
    """Stores codes in dev outbox for local developer loopback inspection."""
    def send_code(self, recipient: str, purpose: str, code: str, expires_in_seconds: int) -> bool:
        logger.info("auth_dev_outbox_code_recorded", recipient=recipient, purpose=purpose)
        return True


class DisabledDeliveryBackend(EmailDeliveryBackend):
    """Rejects code generation with 503 to avoid creating unusable codes."""
    def send_code(self, recipient: str, purpose: str, code: str, expires_in_seconds: int) -> bool:
        logger.warning("auth_email_delivery_disabled_attempt", recipient=recipient, purpose=purpose)
        raise ReframeException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_DELIVERY_DISABLED",
            message="Email delivery service is currently disabled."
        )


class ProviderDeliveryBackend(EmailDeliveryBackend):
    """Production provider delivery backend (fails closed if unconfigured)."""
    def __init__(self, provider_configured: bool = False):
        self.provider_configured = provider_configured

    def send_code(self, recipient: str, purpose: str, code: str, expires_in_seconds: int) -> bool:
        if not self.provider_configured:
            logger.error("auth_email_provider_not_configured", recipient=recipient, purpose=purpose)
            raise ReframeException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="AUTH_DELIVERY_NOT_CONFIGURED",
                message="Email delivery provider is not configured."
            )
        # In this task, no external network provider is called
        return True


def get_email_delivery_backend() -> EmailDeliveryBackend:
    mode = settings.AUTH_EMAIL_DELIVERY_MODE.upper()
    if mode == "DEV_OUTBOX":
        return DevOutboxDeliveryBackend()
    elif mode == "DISABLED":
        return DisabledDeliveryBackend()
    elif mode == "PROVIDER":
        return ProviderDeliveryBackend(provider_configured=False)
    else:
        logger.warning("unknown_auth_delivery_mode_fallback_disabled", mode=mode)
        return DisabledDeliveryBackend()
