"""In-memory execution audit store for isolated development and deterministic tests."""

from __future__ import annotations

from collections.abc import Sequence

from execution.service import ExecutionAuditStore
from providers.execution import AccountSnapshot, ExecutionOrder, OrderRequest, PositionSnapshot


class InMemoryExecutionAuditStore(ExecutionAuditStore):
    def __init__(self) -> None:
        self._reserved: set[str] = set()
        self.orders: list[ExecutionOrder] = []
        self.portfolios: list[tuple[AccountSnapshot, tuple[PositionSnapshot, ...]]] = []

    async def reserve_order(self, request: OrderRequest, *, strategy: str | None, signal_timestamp: object) -> bool:
        del strategy, signal_timestamp
        if request.client_order_id in self._reserved:
            return False
        self._reserved.add(request.client_order_id)
        return True

    async def record_order(self, order: ExecutionOrder) -> None:
        self.orders.append(order)

    async def record_failure(self, client_order_id: str, reason: str) -> None:
        del client_order_id, reason

    async def record_portfolio(
        self, account: AccountSnapshot, positions: Sequence[PositionSnapshot]
    ) -> None:
        self.portfolios.append((account, tuple(positions)))

    async def list_orders(self, limit: int = 100) -> Sequence[ExecutionOrder]:
        return tuple(self.orders[-limit:][::-1])
