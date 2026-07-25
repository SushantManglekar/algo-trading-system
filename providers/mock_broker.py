"""Deterministic paper-like broker for local pipeline tests without credentials."""

from __future__ import annotations

from decimal import Decimal

from providers.execution import (
    AccountSnapshot,
    ExecutionOrder,
    ExecutionProvider,
    OrderLifecycleStatus,
    OrderRequest,
    PositionSnapshot,
)


class MockBrokerageProvider(ExecutionProvider):
    """Acknowledges configured orders without external side effects or hidden fills."""

    @property
    def is_paper(self) -> bool:
        return True

    async def submit_market_order(self, request: OrderRequest) -> ExecutionOrder:
        return ExecutionOrder(
            client_order_id=request.client_order_id,
            broker_order_id=f"mock-{request.client_order_id}",
            symbol=request.symbol,
            quantity=request.quantity,
            side=request.side,
            status=OrderLifecycleStatus.SUBMITTED,
        )

    async def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(
            account_id="mock-paper-account",
            cash=Decimal(100_000),
            equity=Decimal(100_000),
            buying_power=Decimal(100_000),
        )

    async def list_positions(self) -> tuple[PositionSnapshot, ...]:
        return ()

    async def close_position(self, symbol: str, client_order_id: str) -> ExecutionOrder:
        raise ValueError(f"no open mock position exists for {symbol}")
