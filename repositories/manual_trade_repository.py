"""SQLAlchemy repository for the user-operated manual trade journal."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from journal.types import ManualTrade, ManualTradeSide, ManualTradeStatus
from models.manual_trade import ManualTradeRecord
from storage.time import as_utc


class SqlAlchemyManualTradeRepository:
    """Persists journal records without placing, modifying, or cancelling broker orders."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, trade: ManualTrade) -> ManualTrade:
        async with self._sessions() as session:
            session.add(
                ManualTradeRecord(
                    trade_id=trade.trade_id,
                    symbol=trade.symbol,
                    side=trade.side.value,
                    status=trade.status.value,
                    entry_at=trade.entry_at,
                    entry_price=trade.entry_price,
                    quantity=trade.quantity,
                    exit_at=trade.exit_at,
                    exit_price=trade.exit_price,
                    notes=trade.notes,
                    tags=list(trade.tags),
                    created_at=trade.created_at,
                    updated_at=trade.updated_at,
                )
            )
            await session.commit()
        return trade

    async def list_trades(self, symbol: str | None = None) -> Sequence[ManualTrade]:
        statement = select(ManualTradeRecord)
        if symbol is not None:
            statement = statement.where(ManualTradeRecord.symbol == symbol.upper())
        statement = statement.order_by(ManualTradeRecord.entry_at.desc(), ManualTradeRecord.trade_id.desc())
        async with self._sessions() as session:
            records = (await session.scalars(statement)).all()
        return tuple(self._to_domain(record) for record in records)

    @staticmethod
    def _to_domain(record: ManualTradeRecord) -> ManualTrade:
        return ManualTrade(
            trade_id=record.trade_id,
            symbol=record.symbol,
            side=ManualTradeSide(record.side),
            status=ManualTradeStatus(record.status),
            entry_at=as_utc(record.entry_at),
            entry_price=record.entry_price,
            quantity=record.quantity,
            exit_at=as_utc(record.exit_at) if record.exit_at is not None else None,
            exit_price=record.exit_price,
            notes=record.notes,
            tags=tuple(record.tags),
            created_at=as_utc(record.created_at),
            updated_at=as_utc(record.updated_at),
        )
