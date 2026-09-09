"""
Reframe V7 Auth Rate Limiting
Enforces Redis-backed rate limiting on sensitive auth endpoints (signup, login).
Safe fallback in development/test environments; fail-closed in production.
Zero Paid Model Calls.
"""
from fastapi import Request, status
import structlog
from src.reframe.shared.config import settings
from src.reframe.shared.redis_client import redis_client
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes

logger = structlog.get_logger(__name__)


async def check_auth_rate_limit(
    request: Request,
    action: str = "login",
    max_requests: int = 10,
    window_seconds: int = 60
) -> None:
    """
    Checks rate limit for the client IP.
    Raises ReframeException(429) if exceeded.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    key = f"rate_limit:auth:{action}:{client_ip}"

    try:
        current_count = await redis_client.incr(key, ex=window_seconds)
        if current_count > max_requests:
            logger.warning("auth_rate_limit_exceeded", action=action, client_ip=client_ip, count=current_count)
            raise ReframeException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="RATE_LIMIT_EXCEEDED",
                message=f"Too many {action} attempts. Please wait {window_seconds} seconds before retrying."
            )
    except ReframeException:
        raise
    except Exception as e:
        if settings.ENVIRONMENT == "production":
            logger.error("auth_rate_limit_backend_error_in_production", error=str(e))
            raise ReframeException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code=ReframeErrorCodes.INTERNAL_ERROR,
                message="Authentication rate limiting service temporarily unavailable."
            )
        else:
            logger.debug("auth_rate_limit_dev_pass_through", error=str(e))
