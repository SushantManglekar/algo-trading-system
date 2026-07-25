"""SQLAlchemy candle store with a Redis latest-candle cache."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_data.types import Candle, CandleInterval
from models.candle import CandleRecord
from storage.redis_cache import RedisCache
from storage.time import as_utc


class SqlAlchemyCandleStore:
    """Durably upserts in-progress candles and preserves completed candle history."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], cache: RedisCache | None = None) -> None:
        self._sessions = sessions
        self._cache = cache

    async def upsert(self, candle: Candle) -> None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(CandleRecord).where(
                    CandleRecord.symbol == candle.symbol,
                    CandleRecord.interval == candle.interval.value,
                    CandleRecord.start_at == candle.start_at,
                )
            )
            values = {
                "end_at": candle.end_at,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "is_complete": candle.is_complete,
            }
            if record is None:
                session.add(
                    CandleRecord(
                        symbol=candle.symbol,
                        interval=candle.interval.value,
                        start_at=candle.start_at,
                        **values,
                    )
                )
            else:
                for name, value in values.items():
                    setattr(record, name, value)
            await session.commit()
        if self._cache is not None:
            await self._cache.set_json(
                self._cache.key("candle", "latest", candle.symbol, candle.interval.value),
                candle.model_dump_json(),
                ttl_seconds=300,
            )

    async def latest(self, symbol: str, interval: CandleInterval) -> Candle | None:
        normalized_symbol = symbol.upper()
        cache_key = self._cache.key("candle", "latest", normalized_symbol, interval.value) if self._cache else ""
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                return Candle.model_validate_json(cached)
        async with self._sessions() as session:
            record = await session.scalar(
                select(CandleRecord)
                .where(CandleRecord.symbol == normalized_symbol, CandleRecord.interval == interval.value)
                .order_by(CandleRecord.start_at.desc())
            )
        if record is None:
            return None
        candle = self._to_domain(record)
        if self._cache is not None:
            await self._cache.set_json(cache_key, candle.model_dump_json(), ttl_seconds=300)
        return candle

    async def list_candles(
        self, symbol: str, interval: CandleInterval, start_at: datetime, end_at: datetime
    ) -> Sequence[Candle]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(CandleRecord)
                    .where(
                        CandleRecord.symbol == symbol.upper(),
                        CandleRecord.interval == interval.value,
                        CandleRecord.start_at >= start_at,
                        CandleRecord.end_at <= end_at,
                    )
                    .order_by(CandleRecord.start_at.asc())
                )
            ).all()
        return tuple(self._to_domain(record) for record in records)

    @staticmethod
    def _to_domain(record: CandleRecord) -> Candle:
        return Candle(
            symbol=record.symbol,
            interval=CandleInterval(record.interval),
            start_at=as_utc(record.start_at),
            end_at=as_utc(record.end_at),
            open=record.open,
            high=record.high,
            low=record.low,
            close=record.close,
            volume=record.volume,
            is_complete=record.is_complete,
        )
