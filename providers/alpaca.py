"""Alpaca SDK adapter construction with explicit paper/live safety gates."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from config.settings import AppSettings, TradingMode
from providers.execution import ExecutionProvider, OrderSide


class AlpacaExecutionProvider(ExecutionProvider):
    """Alpaca execution adapter; order submission stays disabled unless explicitly enabled."""

    def __init__(self, settings: AppSettings) -> None:
        if settings.execution_provider != "alpaca":
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

    async def submit_market_order(self, symbol: str, quantity: Decimal, side: OrderSide) -> str:
        if not self._settings.order_submission_enabled:
            raise PermissionError("order submission is disabled by configuration")
        order = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=quantity,
            side=AlpacaOrderSide.BUY if side is OrderSide.BUY else AlpacaOrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        response = await asyncio.to_thread(self._client.submit_order, order_data=order)
        return str(response.id)
