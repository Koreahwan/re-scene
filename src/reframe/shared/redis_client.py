"""
Reframe V7 Redis Cache, Rate Limiting & SSE Pub/Sub Client
Implements production fail-closed semantics and local development in-memory fallback.
Zero Paid Model Calls.
"""
import asyncio
import json
import time
from typing import Any, Dict, Optional
import redis.asyncio as aioredis
import structlog
from src.reframe.shared.config import settings

logger = structlog.get_logger(__name__)


class InMemoryFallbackCache:
    """In-memory cache & event bus fallback when Redis is absent in local dev/tests"""
    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._subscribers: Dict[str, list] = {}

    def _purge_expired(self, key: str):
        if key in self._expiry and time.time() > self._expiry[key]:
            self._store.pop(key, None)
            self._expiry.pop(key, None)

    async def get(self, key: str) -> Optional[str]:
        self._purge_expired(key)
        val = self._store.get(key)
        if val is None:
            return None
        return str(val)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self._store[key] = value
        if ex is not None:
            self._expiry[key] = time.time() + ex
        elif key in self._expiry:
            del self._expiry[key]
        return True

    async def incr(self, key: str, ex: Optional[int] = None) -> int:
        self._purge_expired(key)
        val = int(self._store.get(key, 0)) + 1
        self._store[key] = str(val)
        if ex is not None and key not in self._expiry:
            self._expiry[key] = time.time() + ex
        return val

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                self._expiry.pop(k, None)
                count += 1
        return count

    async def publish(self, channel: str, message: str) -> int:
        subs = self._subscribers.get(channel, [])
        for q in subs:
            await q.put(message)
        return len(subs)

    def subscribe(self, channel: str):
        q = asyncio.Queue()
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue):
        if channel in self._subscribers and q in self._subscribers[channel]:
            self._subscribers[channel].remove(q)


class RedisClient:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._fallback = InMemoryFallbackCache()
        self._use_fallback = False

    @property
    def is_real_redis(self) -> bool:
        return self._redis is not None and not self._use_fallback

    async def connect(self):
        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.5
            )
            await self._redis.ping()
            self._use_fallback = False
            logger.info("Connected to Redis successfully", url=settings.REDIS_URL)
        except Exception as e:
            if settings.ENVIRONMENT == "production":
                logger.error("Production Redis connection failed; transparent in-memory fallback is disabled in production", error=str(e))
                self._use_fallback = True
                self._redis = None
            else:
                logger.warning("Redis unavailable; using in-memory local fallback cache", error=str(e))
                self._use_fallback = True
                self._redis = None

    async def close(self):
        if self._redis:
            await self._redis.close()

    async def get(self, key: str) -> Optional[str]:
        if self._use_fallback or not self._redis:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Redis connection required in production mode.")
            return await self._fallback.get(key)
        try:
            return await self._redis.get(key)
        except Exception as e:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(f"Redis get failed in production: {e}")
            return await self._fallback.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if self._use_fallback or not self._redis:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Redis connection required in production mode.")
            return await self._fallback.set(key, value, ex=ex)
        try:
            return await self._redis.set(key, value, ex=ex)
        except Exception as e:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(f"Redis set failed in production: {e}")
            return await self._fallback.set(key, value, ex=ex)

    async def incr(self, key: str, ex: Optional[int] = None) -> int:
        if self._use_fallback or not self._redis:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Redis connection required in production mode.")
            return await self._fallback.incr(key, ex=ex)
        try:
            val = await self._redis.incr(key)
            if ex is not None and val == 1:
                await self._redis.expire(key, ex)
            return val
        except Exception as e:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(f"Redis incr failed in production: {e}")
            return await self._fallback.incr(key, ex=ex)

    async def delete(self, *keys: str) -> int:
        if self._use_fallback or not self._redis:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Redis connection required in production mode.")
            return await self._fallback.delete(*keys)
        try:
            return await self._redis.delete(*keys)
        except Exception as e:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(f"Redis delete failed in production: {e}")
            return await self._fallback.delete(*keys)

    async def publish(self, channel: str, message: str) -> int:
        if self._use_fallback or not self._redis:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Redis connection required in production mode.")
            return await self._fallback.publish(channel, message)
        try:
            return await self._redis.publish(channel, message)
        except Exception as e:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(f"Redis publish failed in production: {e}")
            return await self._fallback.publish(channel, message)


redis_client = RedisClient()
