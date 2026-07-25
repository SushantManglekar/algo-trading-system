"""Composition root for application services and infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass

from analytics.engine import AnalyticsEngine
from analytics.outcome_store import InMemoryOutcomeStore, OutcomeStore
from analytics.types import AnalyticsSettings
from config.settings import AppSettings, StorageBackend
from core.metrics import ApiMetrics
from events.live_hub import LiveEventHub
from market_data.candle_engine import CandleEngine, CandleEngineSettings
from market_data.candle_history import HistoricalCandleService
from market_data.candle_store import CandleStore, InMemoryCandleStore
from market_data.exchange_calendar import XnysExchangeCalendar
from market_data.provider import MarketDataProvider
from market_data.tick_processor import TickProcessor, TickProcessorSettings
from market_data.tick_store import InMemoryTickStore, TickStore
from market_data.types import CandleInterval
from providers.mock import MockMarketDataProvider
from repositories.candle_repository import SqlAlchemyCandleStore
from repositories.outcome_repository import SqlAlchemyOutcomeStore
from repositories.signal_repository import SqlAlchemySignalStore
from repositories.tick_repository import SqlAlchemyTickStore
from risk.engine import RiskEngine
from signals.store import InMemorySignalStore, SignalStore
from storage.database import Database
from storage.redis_cache import RedisCache


@dataclass(slots=True)
class ApplicationContainer:
    """All explicit runtime dependencies owned by one FastAPI application instance."""

    settings: AppSettings
    provider: MarketDataProvider
    tick_store: TickStore
    tick_processor: TickProcessor
    candle_engine: CandleEngine
    candle_store: CandleStore
    candle_history: HistoricalCandleService
    signal_store: SignalStore
    risk_engine: RiskEngine
    analytics_engine: AnalyticsEngine
    metrics: ApiMetrics
    live_hub: LiveEventHub
    database: Database | None = None
    cache: RedisCache | None = None
    started: bool = False

    async def start(self) -> None:
        if self.cache is not None:
            await self.cache.start()
        await self.provider.connect()
        self.started = True

    async def stop(self) -> None:
        await self.provider.disconnect()
        if self.cache is not None:
            await self.cache.close()
        if self.database is not None:
            await self.database.dispose()
        self.started = False


def build_container(settings: AppSettings | None = None) -> ApplicationContainer:
    """Build explicitly selected memory stores or durable PostgreSQL/Redis adapters."""
    resolved_settings = settings or AppSettings()
    calendar = XnysExchangeCalendar()
    database: Database | None = None
    cache: RedisCache | None = None
    if resolved_settings.storage_backend is StorageBackend.POSTGRES:
        database = Database(resolved_settings.database_url)
        cache = RedisCache(resolved_settings.redis_url)
        tick_store: TickStore = SqlAlchemyTickStore(database.sessions, cache)
        candle_store: CandleStore = SqlAlchemyCandleStore(database.sessions, cache)
        signal_store: SignalStore = SqlAlchemySignalStore(database.sessions)
        outcome_store: OutcomeStore = SqlAlchemyOutcomeStore(database.sessions)
    else:
        tick_store = InMemoryTickStore(resolved_settings.tick_buffer_per_symbol)
        candle_store = InMemoryCandleStore(resolved_settings.candle_buffer_per_series)
        signal_store = InMemorySignalStore()
        outcome_store = InMemoryOutcomeStore()
    return ApplicationContainer(
        settings=resolved_settings,
        provider=MockMarketDataProvider(),
        tick_store=tick_store,
        tick_processor=TickProcessor(tick_store, TickProcessorSettings()),
        candle_engine=CandleEngine(CandleEngineSettings(intervals=tuple(CandleInterval)), calendar),
        candle_store=candle_store,
        candle_history=HistoricalCandleService(calendar),
        signal_store=signal_store,
        risk_engine=RiskEngine(resolved_settings.risk_policy()),
        analytics_engine=AnalyticsEngine(
            AnalyticsSettings(
                starting_equity=resolved_settings.analytics_starting_equity,
                reporting_timezone=resolved_settings.analytics_reporting_timezone,
            ),
            outcome_store,
        ),
        metrics=ApiMetrics(),
        live_hub=LiveEventHub(),
        database=database,
        cache=cache,
    )
