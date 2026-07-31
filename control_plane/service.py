"""Applies validated, audited dashboard configuration to the running application."""

from __future__ import annotations

from asyncio import Lock
from collections.abc import Awaitable, Callable, Sequence

from config.settings import AppSettings, TradingMode
from control_plane.repository import TradingControlStore
from control_plane.types import (
    EmaStrategyConfiguration,
    RuntimeTradingConfiguration,
    TradingConfigurationAudit,
    TradingConfigurationUpdate,
)

ApplyConfiguration = Callable[[RuntimeTradingConfiguration], Awaitable[None]]


class TradingControlService:
    """Owns validation, optimistic updates, runtime application, and audit retrieval."""

    def __init__(
        self,
        store: TradingControlStore,
        default_configuration: RuntimeTradingConfiguration,
        apply_configuration: ApplyConfiguration,
    ) -> None:
        self._store = store
        self._default_configuration = default_configuration
        self._apply_configuration = apply_configuration
        self._update_lock = Lock()

    async def start(self) -> RuntimeTradingConfiguration:
        configuration = await self._store.get_or_create(self._default_configuration)
        await self._apply_configuration(configuration)
        return configuration

    async def get(self) -> RuntimeTradingConfiguration:
        return await self._store.get_or_create(self._default_configuration)

    async def update(self, update: TradingConfigurationUpdate) -> RuntimeTradingConfiguration:
        async with self._update_lock:
            current = await self.get()
            candidate = update.to_configuration(version=current.version + 1)
            self._validate_transition(current, candidate, update)
            await self._apply_configuration(candidate)
            try:
                return await self._store.update(candidate, expected_version=update.expected_version)
            except Exception:
                await self._apply_configuration(current)
                raise

    async def list_audit(self, limit: int = 50) -> Sequence[TradingConfigurationAudit]:
        return await self._store.list_audit(limit)

    @staticmethod
    def from_settings(settings: AppSettings) -> RuntimeTradingConfiguration:
        return RuntimeTradingConfiguration(
            mode=settings.trading_mode,
            place_orders_automatically=settings.automation_enabled,
            monitoring_enabled=bool(settings.symbols),
            symbols=settings.symbols,
            strategy=EmaStrategyConfiguration(
                interval=settings.strategy_interval,
                fast_period=settings.ema_fast_period,
                slow_period=settings.ema_slow_period,
                base_confidence=settings.ema_base_confidence,
                confidence_sensitivity=settings.ema_confidence_sensitivity,
                max_confidence=settings.ema_max_confidence,
            ),
            risk_policy=settings.risk_policy(),
        )

    @staticmethod
    def _validate_transition(
        current: RuntimeTradingConfiguration,
        candidate: RuntimeTradingConfiguration,
        update: TradingConfigurationUpdate,
    ) -> None:
        if update.expected_version != current.version:
            raise ValueError("configuration version conflict; reload before saving")
        entering_live = candidate.mode is TradingMode.LIVE and current.mode is not TradingMode.LIVE
        if entering_live and update.live_confirmation != "ENABLE_LIVE_TRADING":
            raise ValueError("live mode requires explicit ENABLE_LIVE_TRADING confirmation")
        enabling_automation = candidate.place_orders_automatically and (
            not current.place_orders_automatically or candidate.mode is not current.mode
        )
        if enabling_automation:
            expected = (
                "ENABLE_LIVE_AUTOMATION"
                if candidate.mode is TradingMode.LIVE
                else "ENABLE_PAPER_AUTOMATION"
            )
            if update.automation_confirmation != expected:
                raise ValueError(f"automatic orders require explicit {expected} confirmation")
