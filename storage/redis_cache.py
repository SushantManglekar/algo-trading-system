"""Small Redis cache adapter for reconstructible, non-authoritative values."""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError


class RedisCache:
    """JSON cache. PostgreSQL remains authoritative when a key is absent or expires."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Redis | None = None

    async def start(self) -> None:
        self._client = Redis.from_url(self._url, decode_responses=True)
        await self._client.ping()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_json(self, key: str) -> str | None:
        if self._client is None:
            return None
        try:
            value = await self._client.get(key)
        except RedisError:
            return None
        return value if isinstance(value, str) else None

    async def set_json(self, key: str, value: str, *, ttl_seconds: int) -> None:
        if self._client is not None:
            try:
                await self._client.set(key, value, ex=ttl_seconds)
            except RedisError:
                pass

    async def delete(self, *keys: str) -> None:
        if self._client is not None and keys:
            try:
                await self._client.delete(*keys)
            except RedisError:
                pass

    async def publish_json(self, channel: str, payload: str) -> None:
        if self._client is not None:
            try:
                await self._client.publish(channel, payload)
            except RedisError:
                pass

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    @staticmethod
    def key(*parts: Any) -> str:
        """Build namespaced keys without allowing separators in variable components."""
        return "trading:" + ":".join(str(part).replace(":", "_") for part in parts)
