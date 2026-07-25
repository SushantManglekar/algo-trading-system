"""SQLAlchemy audit store for account snapshots and idempotent execution orders."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.execution import AccountSnapshotRecord, ExecutionOrderRecord, PositionSnapshotRecord
from providers.execution import (
    AccountSnapshot,
    ExecutionOrder,
    OrderLifecycleStatus,
    OrderRequest,
    OrderSide,
    PositionSnapshot,
)
from storage.time import as_utc


class SqlAlchemyExecutionRepository:
    """Persists submission intent before broker I/O so retries never blindly duplicate an order."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def reserve_order(self, request: OrderRequest, *, strategy: str | None, signal_timestamp: datetime | None) -> bool:
        now = datetime.now(UTC)
        async with self._sessions() as session:
            session.add(
                ExecutionOrderRecord(
                    client_order_id=request.client_order_id,
                    symbol=request.symbol,
                    quantity=request.quantity,
                    side=request.side.value,
                    status=OrderLifecycleStatus.PENDING.value,
                    strategy=strategy,
                    signal_timestamp=signal_timestamp,
                    filled_quantity=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
        return True

    async def record_order(self, order: ExecutionOrder) -> None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(ExecutionOrderRecord).where(ExecutionOrderRecord.client_order_id == order.client_order_id)
            )
            if record is None:
                raise ValueError("order must be reserved before recording broker state")
            record.broker_order_id = order.broker_order_id
            record.status = order.status.value
            record.submitted_at = order.submitted_at
            record.filled_at = order.filled_at
            record.filled_quantity = order.filled_quantity
            record.average_fill_price = order.average_fill_price
            record.reason = order.reason
            record.updated_at = datetime.now(UTC)
            await session.commit()

    async def record_failure(self, client_order_id: str, reason: str) -> None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(ExecutionOrderRecord).where(ExecutionOrderRecord.client_order_id == client_order_id)
            )
            if record is None:
                return
            record.status = OrderLifecycleStatus.FAILED.value
            record.reason = reason[:1_000]
            record.updated_at = datetime.now(UTC)
            await session.commit()

    async def list_orders(self, limit: int = 100) -> Sequence[ExecutionOrder]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(ExecutionOrderRecord)
                    .order_by(ExecutionOrderRecord.created_at.desc())
                    .limit(limit)
                )
            ).all()
        return tuple(self._to_order(record) for record in records)

    async def record_portfolio(self, account: AccountSnapshot, positions: Sequence[PositionSnapshot]) -> None:
        async with self._sessions() as session:
            session.add(
                AccountSnapshotRecord(
                    account_id=account.account_id,
                    cash=account.cash,
                    equity=account.equity,
                    buying_power=account.buying_power,
                    previous_close_equity=account.previous_close_equity,
                    updated_at=account.updated_at,
                )
            )
            session.add_all(
                PositionSnapshotRecord(
                    account_id=account.account_id,
                    symbol=position.symbol,
                    quantity=position.quantity,
                    average_entry_price=position.average_entry_price,
                    market_value=position.market_value,
                    cost_basis=position.cost_basis,
                    unrealized_pnl=position.unrealized_pnl,
                    unrealized_pnl_percent=position.unrealized_pnl_percent,
                    updated_at=account.updated_at,
                )
                for position in positions
            )
            await session.commit()

    @staticmethod
    def _to_order(record: ExecutionOrderRecord) -> ExecutionOrder:
        return ExecutionOrder(
            client_order_id=record.client_order_id,
            broker_order_id=record.broker_order_id,
            symbol=record.symbol,
            quantity=record.quantity,
            side=OrderSide(record.side),
            status=OrderLifecycleStatus(record.status),
            submitted_at=as_utc(record.submitted_at) if record.submitted_at else None,
            filled_at=as_utc(record.filled_at) if record.filled_at else None,
            filled_quantity=record.filled_quantity,
            average_fill_price=record.average_fill_price,
            reason=record.reason,
        )
