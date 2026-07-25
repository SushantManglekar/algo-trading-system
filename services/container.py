"""Composition root for application services and infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass

from analytics.engine import AnalyticsEngine
from analytics.types import AnalyticsSettings
from config.settings import AppSettings
from core.metrics import ApiMetrics
from events.live_hub import LiveEventHub
from market_data.candle_engine import CandleEngine, CandleEngineSettings
from market_data.candle_history import HistoricalCandleService
from market_data.candle_store import InMemoryCandleStore
from market_data.exchange_calendar import XnysExchangeCalendar
from market_data.tick_processor import TickProcessor, TickProcessorSettings
from market_data.tick_store import InMemoryTickStore
from market_data.types import CandleInterval
from providers.mock import MockMarketDataProvider
from risk.engine import RiskEngine
from signals.store import InMemorySignalStore


@dataclass(slots=True)
class ApplicationContainer:
    """All explicit runtime dependencies owned by one FastAPI application instance."""

    settings: AppSettings
    provider: MockMarketDataProvider
    tick_store: InMemoryTickStore
    tick_processor: TickProcessor
    candle_engine: CandleEngine
    candle_store: InMemoryCandleStore
    candle_history: HistoricalCandleService
    signal_store: InMemorySignalStore
    risk_engine: RiskEngine
    analytics_engine: AnalyticsEngine
    metrics: ApiMetrics
    live_hub: LiveEventHub
    started: bool = False

    async def start(self) -> None:
        await self.provider.connect()
        self.started = True

    async def stop(self) -> None:
        await self.provider.disconnect()
        self.started = False


def build_container(settings: AppSettings | None = None) -> ApplicationContainer:
    """Build the default development composition; production adapters replace these inputs."""
    resolved_settings = settings or AppSettings()
    calendar = XnysExchangeCalendar()
    tick_store = InMemoryTickStore(resolved_settings.tick_buffer_per_symbol)
    return ApplicationContainer(
        settings=resolved_settings,
        provider=MockMarketDataProvider(),
        tick_store=tick_store,
        tick_processor=TickProcessor(tick_store, TickProcessorSettings()),
        candle_engine=CandleEngine(CandleEngineSettings(intervals=tuple(CandleInterval)), calendar),
        candle_store=InMemoryCandleStore(resolved_settings.candle_buffer_per_series),
        candle_history=HistoricalCandleService(calendar),
        signal_store=InMemorySignalStore(),
        risk_engine=RiskEngine(resolved_settings.risk_policy()),
        analytics_engine=AnalyticsEngine(
            AnalyticsSettings(
                starting_equity=resolved_settings.analytics_starting_equity,
                reporting_timezone=resolved_settings.analytics_reporting_timezone,
            )
        ),
        metrics=ApiMetrics(),
        live_hub=LiveEventHub(),
    )
