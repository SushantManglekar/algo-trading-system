from __future__ import annotations

from decimal import Decimal

import pytest

from config.settings import AppSettings, TradingMode
from control_plane.repository import InMemoryTradingControlStore
from control_plane.service import TradingControlService
from control_plane.types import RuntimeTradingConfiguration, TradingConfigurationUpdate


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        symbols="AAPL",
        analytics_starting_equity=Decimal(10_000),
        tick_buffer_per_symbol=100,
        candle_buffer_per_series=100,
    )


def _update(
    configuration: RuntimeTradingConfiguration, **overrides: object
) -> TradingConfigurationUpdate:
    payload: dict[str, object] = {
        "mode": configuration.mode,
        "place_orders_automatically": configuration.place_orders_automatically,
        "monitoring_enabled": configuration.monitoring_enabled,
        "symbols": configuration.symbols,
        "strategy": configuration.strategy,
        "risk_policy": configuration.risk_policy,
        "expected_version": configuration.version,
    }
    payload.update(overrides)
    return TradingConfigurationUpdate.model_validate(payload)


@pytest.mark.asyncio
async def test_control_updates_are_applied_audited_and_versioned() -> None:
    applied: list[RuntimeTradingConfiguration] = []

    async def apply(configuration: RuntimeTradingConfiguration) -> None:
        applied.append(configuration)

    service = TradingControlService(
        InMemoryTradingControlStore(), TradingControlService.from_settings(_settings()), apply
    )
    initial = await service.start()
    updated = await service.update(_update(initial, symbols=("msft",), monitoring_enabled=False))

    assert updated.symbols == ("MSFT",)
    assert updated.version == 2
    assert applied == [initial, updated]
    assert [item.version for item in await service.list_audit()] == [2, 1]


@pytest.mark.asyncio
async def test_live_and_automatic_orders_require_explicit_runtime_confirmations() -> None:
    async def apply(_: RuntimeTradingConfiguration) -> None:
        return None

    service = TradingControlService(
        InMemoryTradingControlStore(), TradingControlService.from_settings(_settings()), apply
    )
    initial = await service.start()

    with pytest.raises(ValueError, match="ENABLE_LIVE_TRADING"):
        await service.update(_update(initial, mode=TradingMode.LIVE))

    live = await service.update(
        _update(initial, mode=TradingMode.LIVE, live_confirmation="ENABLE_LIVE_TRADING")
    )
    with pytest.raises(ValueError, match="ENABLE_LIVE_AUTOMATION"):
        await service.update(_update(live, place_orders_automatically=True))


@pytest.mark.asyncio
async def test_control_rejects_stale_dashboard_writes() -> None:
    async def apply(_: RuntimeTradingConfiguration) -> None:
        return None

    service = TradingControlService(
        InMemoryTradingControlStore(), TradingControlService.from_settings(_settings()), apply
    )
    initial = await service.start()
    await service.update(_update(initial, monitoring_enabled=False))

    with pytest.raises(ValueError, match="version conflict"):
        await service.update(_update(initial, monitoring_enabled=True))
