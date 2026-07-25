"""Alpaca SDK adapter construction with explicit paper/live safety gates."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from config.settings import AppSettings, ProviderName, TradingMode
from providers.execution import (
    AccountSnapshot,
    ExecutionOrder,
    ExecutionProvider,
    OrderLifecycleStatus,
    OrderRequest,
    OrderSide,
    PositionSnapshot,
)


class AlpacaExecutionProvider(ExecutionProvider):
    """Alpaca execution adapter; order submission stays disabled unless explicitly enabled."""

    def __init__(self, settings: AppSettings) -> None:
        if settings.execution_provider is not ProviderName.ALPACA:
            raise ValueError("Alpaca adapter requires execution_provider=alpaca")
        if settings.alpaca_api_key is None or settings.alpaca_api_secret is None:
            raise ValueError("Alpaca API credentials are required")
        self._settings = settings
        self._client = TradingClient(
            settings.alpaca_api_key.get_secret_value(),
            settings.alpaca_api_secret.get_secret_value(),
            paper=settings.trading_mode is TradingMode.PAPER,
        )

    @property
    def is_paper(self) -> bool:
        return self._settings.trading_mode is TradingMode.PAPER

    async def submit_market_order(self, request: OrderRequest) -> ExecutionOrder:
        if not self._settings.order_submission_enabled:
            raise PermissionError("order submission is disabled by configuration")
        order = MarketOrderRequest(
            symbol=request.symbol,
            qty=float(request.quantity),
            side=AlpacaOrderSide.BUY if request.side is OrderSide.BUY else AlpacaOrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=request.client_order_id,
        )
        response = await asyncio.to_thread(self._client.submit_order, order_data=order)
        return self._to_execution_order(response, request)

    async def get_account(self) -> AccountSnapshot:
        account = await asyncio.to_thread(self._client.get_account)
        return AccountSnapshot(
            account_id=str(account.id),
            cash=Decimal(str(account.cash)),
            equity=Decimal(str(account.equity)),
            buying_power=Decimal(str(account.buying_power)),
            previous_close_equity=(
                Decimal(str(account.last_equity)) if account.last_equity is not None else None
            ),
            updated_at=datetime.now(UTC),
        )

    async def list_positions(self) -> tuple[PositionSnapshot, ...]:
        positions = await asyncio.to_thread(self._client.get_all_positions)
        return tuple(
            PositionSnapshot(
                symbol=position.symbol,
                quantity=Decimal(str(position.qty)),
                average_entry_price=Decimal(str(position.avg_entry_price)),
                market_value=Decimal(str(position.market_value)),
                cost_basis=Decimal(str(position.cost_basis)),
                unrealized_pnl=Decimal(str(position.unrealized_pl)),
                unrealized_pnl_percent=Decimal(str(position.unrealized_plpc)),
            )
            for position in positions
        )

    async def close_position(self, symbol: str, client_order_id: str) -> ExecutionOrder:
        if not self._settings.order_submission_enabled:
            raise PermissionError("order submission is disabled by configuration")
        positions = await self.list_positions()
        position = next((item for item in positions if item.symbol == symbol.upper()), None)
        if position is None or position.quantity == Decimal(0):
            raise ValueError(f"no open position exists for {symbol.upper()}")
        request = OrderRequest(
            client_order_id=client_order_id,
            symbol=symbol,
            quantity=abs(position.quantity),
            side=OrderSide.SELL if position.quantity > Decimal(0) else OrderSide.BUY,
        )
        return await self.submit_market_order(request)

    @staticmethod
    def _to_execution_order(response: object, request: OrderRequest) -> ExecutionOrder:
        status_value = str(getattr(response, "status", "submitted")).lower()
        statuses = {status.value for status in OrderLifecycleStatus}
        status = OrderLifecycleStatus(status_value) if status_value in statuses else OrderLifecycleStatus.SUBMITTED
        return ExecutionOrder(
            client_order_id=request.client_order_id,
            broker_order_id=str(getattr(response, "id", "")) or None,
            symbol=request.symbol,
            quantity=request.quantity,
            side=request.side,
            status=status,
            submitted_at=getattr(response, "submitted_at", None),
            filled_at=getattr(response, "filled_at", None),
            filled_quantity=Decimal(str(getattr(response, "filled_qty", 0) or 0)),
            average_fill_price=(
                Decimal(str(response.filled_avg_price))
                if getattr(response, "filled_avg_price", None) is not None
                else None
            ),
        )
