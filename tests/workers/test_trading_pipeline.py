import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from config.settings import AppSettings
from market_data.types import MarketTick
from providers.mock import MockMarketDataProvider
from services.container import build_container


def tick(timestamp: datetime, price: int) -> MarketTick:
    return MarketTick(
        timestamp=timestamp,
        received_at=timestamp + timedelta(milliseconds=1),
        symbol="AAPL",
        exchange="NASDAQ",
        price=Decimal(price),
        bid=Decimal(price) - Decimal("0.01"),
        ask=Decimal(price) + Decimal("0.01"),
        volume=Decimal(100),
        trade_size=Decimal(10),
    )


@pytest.mark.asyncio
async def test_symbol_sharded_worker_runs_candle_strategy_risk_and_paper_execution() -> None:
    container = build_container(
        AppSettings(
            symbols="AAPL",
            order_submission_enabled=True,
            automation_enabled=True,
            automation_confirmation="ENABLE_PAPER_AUTOMATION",
            atr_period=2,
            ema_fast_period=2,
            ema_slow_period=3,
        )
    )
    assert isinstance(container.provider, MockMarketDataProvider)
    await container.start()
    try:
        started_at = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
        for offset, price in enumerate((100, 99, 98, 99, 100, 101, 102)):
            assert await container.provider.publish_tick(tick(started_at + timedelta(minutes=offset), price))

        async def has_order() -> bool:
            return bool(await container.execution_audit_store.list_orders())

        for _ in range(100):
            if await has_order():
                break
            await asyncio.sleep(0.01)
        orders = await container.execution_audit_store.list_orders()
        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"
        assert orders[0].side == "buy"
    finally:
        await container.stop()
