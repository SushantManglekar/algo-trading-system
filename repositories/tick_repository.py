"""SQLAlchemy repository for immutable accepted ticks."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_data.types import MarketTick
from models.tick import TickRecord
from storage.redis_cache import RedisCache
from storage.time import as_utc


class SqlAlchemyTickStore:
    """PostgreSQL tick store with Redis acceleration for the latest-price read path."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], cache: RedisCache | None = None) -> None:
        self._sessions = sessions
        self._cache = cache

    async def append(self, tick: MarketTick) -> None:
        async with self._sessions() as session:
            session.add(
                TickRecord(
                    timestamp=tick.timestamp,
                    received_at=tick.received_at,
                    symbol=tick.symbol,
                    exchange=tick.exchange,
                    price=tick.price,
                    bid=tick.bid,
                    ask=tick.ask,
                    volume=tick.volume,
                    trade_size=tick.trade_size,
                    conditions=list(tick.conditions),
                )
            )
            await session.commit()
        if self._cache is not None:
            await self._cache.set_json(
                self._cache.key("tick", "latest", tick.symbol), tick.model_dump_json(), ttl_seconds=300
            )

    async def latest(self, symbol: str) -> MarketTick | None:
        normalized_symbol = symbol.upper()
        cache_key = self._cache.key("tick", "latest", normalized_symbol) if self._cache else ""
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                return MarketTick.model_validate_json(cached)
        async with self._sessions() as session:
            record = await session.scalar(
                select(TickRecord)
                .where(TickRecord.symbol == normalized_symbol)
                .order_by(TickRecord.timestamp.desc(), TickRecord.id.desc())
            )
        if record is None:
            return None
        tick = self._to_domain(record)
        if self._cache is not None:
            await self._cache.set_json(cache_key, tick.model_dump_json(), ttl_seconds=300)
        return tick

    async def list_ticks(
        self,
        symbol: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> Sequence[MarketTick]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive when supplied")
        statement = select(TickRecord).where(TickRecord.symbol == symbol.upper())
        if start_at is not None:
            statement = statement.where(TickRecord.timestamp >= start_at)
        if end_at is not None:
            statement = statement.where(TickRecord.timestamp <= end_at)
        if limit is not None:
            statement = statement.order_by(TickRecord.timestamp.desc(), TickRecord.id.desc()).limit(limit)
        else:
            statement = statement.order_by(TickRecord.timestamp.asc(), TickRecord.id.asc())
        async with self._sessions() as session:
            records = (await session.scalars(statement)).all()
        if limit is not None:
            records.reverse()
        return tuple(self._to_domain(record) for record in records)

    @staticmethod
    def _to_domain(record: TickRecord) -> MarketTick:
        return MarketTick(
            timestamp=as_utc(record.timestamp),
            received_at=as_utc(record.received_at),
            symbol=record.symbol,
            exchange=record.exchange,
            price=record.price,
            bid=record.bid,
            ask=record.ask,
            volume=record.volume,
            trade_size=record.trade_size,
            conditions=tuple(record.conditions),
        )


SqlAlchemyTickRepository = SqlAlchemyTickStore
