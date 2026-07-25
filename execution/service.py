"""Portfolio-aware execution coordinator with durable idempotency reservation."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from config.settings import AppSettings
from providers.execution import (
    AccountSnapshot,
    ExecutionOrder,
    ExecutionProvider,
    OrderRequest,
    PositionSnapshot,
)
from risk.types import RiskContext, RiskManagedSignal
from strategies.types import StrategyDirection, StrategySignalIntent


class ExecutionAuditStore(Protocol):
    """Persistent idempotency and audit boundary for the execution coordinator."""

    async def reserve_order(
        self, request: OrderRequest, *, strategy: str | None, signal_timestamp: datetime | None
    ) -> bool: ...

    async def record_order(self, order: ExecutionOrder) -> None: ...

    async def record_failure(self, client_order_id: str, reason: str) -> None: ...

    async def record_portfolio(
        self, account: AccountSnapshot, positions: Sequence[PositionSnapshot]
    ) -> None: ...

    async def list_orders(self, limit: int = 100) -> Sequence[ExecutionOrder]: ...


class AutomatedExecutionService:
    """Executes only risk-approved entries, with portfolio state re-read at submission time."""

    def __init__(
        self, settings: AppSettings, broker: ExecutionProvider, audit_store: ExecutionAuditStore
    ) -> None:
        self._settings = settings
        self._broker = broker
        self._audit_store = audit_store

    async def risk_context(
        self, *, entry_price: Decimal, atr: Decimal, symbol: str
    ) -> RiskContext:
        account, positions = await self.portfolio()
        matching_position = next((position for position in positions if position.symbol == symbol), None)
        return RiskContext(
            entry_price=entry_price,
            atr=atr,
            account_equity=account.equity,
            daily_realized_pnl=account.daily_pnl,
            consecutive_losses=0,
            available_cash=min(account.cash, account.buying_power),
            gross_exposure=sum(abs(position.market_value) for position in positions),
            open_positions=len(positions),
            has_open_position=matching_position is not None,
            would_average_down=matching_position is not None,
        )

    async def portfolio(self) -> tuple[AccountSnapshot, tuple[PositionSnapshot, ...]]:
        account, positions = await self._broker.get_account(), await self._broker.list_positions()
        resolved_positions = tuple(positions)
        await self._audit_store.record_portfolio(account, resolved_positions)
        return account, resolved_positions

    async def execute_entry(self, signal: RiskManagedSignal) -> ExecutionOrder | None:
        """Reserve first, then submit exactly once for an approved directional entry."""
        if not self._settings.automation_enabled:
            return None
        request = OrderRequest(
            client_order_id=self._client_order_id(signal.symbol, signal.timestamp, signal.strategy, signal.direction),
            symbol=signal.symbol,
            quantity=Decimal(signal.position_size),
            side=signal.direction.value.lower(),
            created_at=datetime.now(UTC),
        )
        reserved = await self._audit_store.reserve_order(
            request, strategy=signal.strategy, signal_timestamp=signal.timestamp
        )
        if not reserved:
            return None
        try:
            order = await self._broker.submit_market_order(request)
        except Exception as error:
            await self._audit_store.record_failure(request.client_order_id, str(error))
            raise
        await self._audit_store.record_order(order)
        await self.portfolio()
        return order

    async def execute_exit(self, intent: StrategySignalIntent) -> ExecutionOrder | None:
        """Close an existing position after an explicit strategy exit; no reverse order is created."""
        if not self._settings.automation_enabled or intent.direction is not StrategyDirection.EXIT:
            return None
        _, positions = await self.portfolio()
        if not any(position.symbol == intent.symbol for position in positions):
            return None
        client_order_id = self._client_order_id(intent.symbol, intent.timestamp, intent.strategy, intent.direction)
        request = OrderRequest(
            client_order_id=client_order_id,
            symbol=intent.symbol,
            quantity=Decimal(1),
            side="sell",
            created_at=datetime.now(UTC),
        )
        if not await self._audit_store.reserve_order(
            request, strategy=intent.strategy, signal_timestamp=intent.timestamp
        ):
            return None
        try:
            order = await self._broker.close_position(intent.symbol, client_order_id)
        except Exception as error:
            await self._audit_store.record_failure(client_order_id, str(error))
            raise
        await self._audit_store.record_order(order)
        await self.portfolio()
        return order

    @staticmethod
    def _client_order_id(
        symbol: str, timestamp: datetime, strategy: str, direction: StrategyDirection
    ) -> str:
        source = f"{symbol}|{timestamp.astimezone(UTC).isoformat()}|{strategy}|{direction.value}"
        return f"ats-{hashlib.sha256(source.encode()).hexdigest()[:40]}"
