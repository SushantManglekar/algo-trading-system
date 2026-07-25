"""SQLAlchemy storage for approved risk-managed signal proposals."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.signal import SignalRecord
from risk.types import RiskManagedSignal
from storage.time import as_utc
from strategies.types import StrategyDirection


class SqlAlchemySignalStore:
    """Stores immutable signals independently from broker execution and outcomes."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(self, signal: RiskManagedSignal) -> None:
        async with self._sessions() as session:
            session.add(
                SignalRecord(
                    symbol=signal.symbol,
                    timestamp=signal.timestamp,
                    strategy=signal.strategy,
                    direction=signal.direction.value,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    atr_stop_loss=signal.atr_stop_loss,
                    trailing_stop_distance=signal.trailing_stop_distance,
                    risk_reward=signal.risk_reward,
                    position_size=signal.position_size,
                    position_risk=signal.position_risk,
                    expected_move=signal.expected_move,
                    confidence=signal.confidence,
                    reason=signal.reason,
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def list_signals(self, symbol: str | None = None) -> Sequence[RiskManagedSignal]:
        statement = select(SignalRecord)
        if symbol is not None:
            statement = statement.where(SignalRecord.symbol == symbol.upper())
        statement = statement.order_by(SignalRecord.timestamp.asc(), SignalRecord.signal_id.asc())
        async with self._sessions() as session:
            records = (await session.scalars(statement)).all()
        return tuple(self._to_domain(record) for record in records)

    @staticmethod
    def _to_domain(record: SignalRecord) -> RiskManagedSignal:
        return RiskManagedSignal(
            symbol=record.symbol,
            timestamp=as_utc(record.timestamp),
            strategy=record.strategy,
            direction=StrategyDirection(record.direction),
            entry_price=record.entry_price,
            stop_loss=record.stop_loss,
            take_profit=record.take_profit,
            atr_stop_loss=record.atr_stop_loss,
            trailing_stop_distance=record.trailing_stop_distance,
            risk_reward=record.risk_reward,
            position_size=record.position_size,
            position_risk=record.position_risk,
            expected_move=record.expected_move,
            confidence=record.confidence,
            reason=record.reason,
        )
