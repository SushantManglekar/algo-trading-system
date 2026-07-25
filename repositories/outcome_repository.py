"""SQLAlchemy persistence for immutable analytics outcomes."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics.types import ClosedSignalOutcome
from models.outcome import SignalOutcomeRecord
from risk.types import RiskManagedSignal
from storage.time import as_utc


class SqlAlchemyOutcomeStore:
    """Stores observed closes; analytics always recalculates from persisted records."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(self, outcome: ClosedSignalOutcome) -> None:
        async with self._sessions() as session:
            session.add(
                SignalOutcomeRecord(
                    outcome_id=outcome.outcome_id,
                    symbol=outcome.signal.symbol,
                    direction=outcome.signal.direction.value,
                    signal_timestamp=outcome.signal.timestamp,
                    signal_payload=outcome.signal.model_dump(mode="json"),
                    exit_price=outcome.exit_price,
                    closed_at=outcome.closed_at,
                    realized_pnl=outcome.realized_pnl,
                    r_multiple=outcome.r_multiple,
                    holding_seconds=outcome.holding_seconds,
                )
            )
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise ValueError("outcome has already been recorded") from error

    async def list_outcomes(self) -> Sequence[ClosedSignalOutcome]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(SignalOutcomeRecord).order_by(
                        SignalOutcomeRecord.closed_at.asc(), SignalOutcomeRecord.outcome_id.asc()
                    )
                )
            ).all()
        return tuple(self._to_domain(record) for record in records)

    @staticmethod
    def _to_domain(record: SignalOutcomeRecord) -> ClosedSignalOutcome:
        return ClosedSignalOutcome(
            outcome_id=record.outcome_id,
            signal=RiskManagedSignal.model_validate(record.signal_payload),
            exit_price=record.exit_price,
            closed_at=as_utc(record.closed_at),
        )
