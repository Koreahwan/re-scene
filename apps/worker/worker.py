"""
Reframe V7 Worker Entrypoint
"""
import asyncio
import signal
import sys
import structlog

from src.reframe.jobs.worker import worker
from src.reframe.shared.redis_client import redis_client

logger = structlog.get_logger(__name__)


def handle_sigterm(*args):
    logger.info("SIGTERM received, shutting down worker gracefully")
    worker.stop()
    sys.exit(0)


async def main():
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)
    logger.info("Starting Reframe V7 Durable Worker...")
    try:
        await redis_client.connect()
        await worker.run_loop()
    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
