"""Composition root for application services and infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass

from analytics.engine import AnalyticsEngine
from analytics.outcome_store import InMemoryOutcomeStore, OutcomeStore
from analytics.types import AnalyticsSettings
from config.settings import AppSettings, ProviderName, StorageBackend
from core.metrics import ApiMetrics
from events.live_hub import LiveEventHub
from execution.in_memory import InMemoryExecutionAuditStore
from execution.service import AutomatedExecutionService, ExecutionAuditStore
from market_data.candle_engine import CandleEngine, CandleEngineSettings
from market_data.candle_history import HistoricalCandleService
from market_data.candle_store import CandleStore, InMemoryCandleStore
from market_data.exchange_calendar import XnysExchangeCalendar
from market_data.provider import MarketDataProvider
from market_data.tick_processor import TickProcessor, TickProcessorSettings
from market_data.tick_store import InMemoryTickStore, TickStore
from market_data.types import CandleInterval
from providers.alpaca import AlpacaExecutionProvider
from providers.alpaca_market_data import AlpacaMarketDataProvider
from providers.execution import ExecutionProvider
from providers.mock import MockMarketDataProvider
from providers.mock_broker import MockBrokerageProvider
from repositories.candle_repository import SqlAlchemyCandleStore
from repositories.execution_repository import SqlAlchemyExecutionRepository
from repositories.outcome_repository import SqlAlchemyOutcomeStore
from repositories.signal_repository import SqlAlchemySignalStore
from repositories.tick_repository import SqlAlchemyTickStore
from risk.engine import RiskEngine
from services.trading_orchestrator import TradingOrchestrator
from signals.store import InMemorySignalStore, SignalStore
from storage.database import Database
from storage.redis_cache import RedisCache
from strategies.ema_crossover import EmaCrossoverSettings, EmaCrossoverStrategy
from strategies.engine import StrategyEngine
from strategies.registry import StrategyRegistry
from workers.trading_pipeline import TradingPipelineWorker


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
    broker: ExecutionProvider
    execution_service: AutomatedExecutionService
    execution_audit_store: ExecutionAuditStore
    trading_orchestrator: TradingOrchestrator
    pipeline_worker: TradingPipelineWorker
    database: Database | None = None
    cache: RedisCache | None = None
    started: bool = False

    async def start(self) -> None:
        if self.cache is not None:
            await self.cache.start()
        await self.provider.connect()
        await self.pipeline_worker.start()
        self.started = True

    async def stop(self) -> None:
        await self.pipeline_worker.stop()
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
        execution_audit_store: ExecutionAuditStore = SqlAlchemyExecutionRepository(database.sessions)
    else:
        tick_store = InMemoryTickStore(resolved_settings.tick_buffer_per_symbol)
        candle_store = InMemoryCandleStore(resolved_settings.candle_buffer_per_series)
        signal_store = InMemorySignalStore()
        outcome_store = InMemoryOutcomeStore()
        execution_audit_store = InMemoryExecutionAuditStore()
    provider: MarketDataProvider
    if resolved_settings.market_data_provider is ProviderName.ALPACA:
        provider = AlpacaMarketDataProvider(resolved_settings)
    else:
        provider = MockMarketDataProvider()
    broker: ExecutionProvider
    if resolved_settings.execution_provider is ProviderName.ALPACA:
        broker = AlpacaExecutionProvider(resolved_settings)
    else:
        broker = MockBrokerageProvider()
    strategy_engines: dict[str, StrategyEngine] = {}
    for symbol in resolved_settings.symbols:
        registry = StrategyRegistry()
        registry.register(
            EmaCrossoverStrategy(
                EmaCrossoverSettings(
                    symbol=symbol,
                    interval=resolved_settings.strategy_interval,
                    fast_period=resolved_settings.ema_fast_period,
                    slow_period=resolved_settings.ema_slow_period,
                    base_confidence=resolved_settings.ema_base_confidence,
                    confidence_sensitivity=resolved_settings.ema_confidence_sensitivity,
                    max_confidence=resolved_settings.ema_max_confidence,
                )
            )
        )
        strategy_engines[symbol] = StrategyEngine(registry)
    risk_engine = RiskEngine(resolved_settings.risk_policy())
    execution_service = AutomatedExecutionService(resolved_settings, broker, execution_audit_store)
    live_hub = LiveEventHub()
    tick_processor = TickProcessor(tick_store, TickProcessorSettings())
    candle_engine = CandleEngine(CandleEngineSettings(intervals=tuple(CandleInterval)), calendar)
    trading_orchestrator = TradingOrchestrator(
        tick_processor,
        candle_engine,
        candle_store,
        signal_store,
        strategy_engines,
        risk_engine,
        execution_service,
        resolved_settings.atr_period,
        live_hub,
    )
    return ApplicationContainer(
        settings=resolved_settings,
        provider=provider,
        tick_store=tick_store,
        tick_processor=tick_processor,
        candle_engine=candle_engine,
        candle_store=candle_store,
        candle_history=HistoricalCandleService(calendar),
        signal_store=signal_store,
        risk_engine=risk_engine,
        analytics_engine=AnalyticsEngine(
            AnalyticsSettings(
                starting_equity=resolved_settings.analytics_starting_equity,
                reporting_timezone=resolved_settings.analytics_reporting_timezone,
            ),
            outcome_store,
        ),
        metrics=ApiMetrics(),
        live_hub=live_hub,
        broker=broker,
        execution_service=execution_service,
        execution_audit_store=execution_audit_store,
        trading_orchestrator=trading_orchestrator,
        pipeline_worker=TradingPipelineWorker(
            provider,
            trading_orchestrator,
            resolved_settings.symbols,
            resolved_settings.worker_count,
            resolved_settings.worker_queue_size,
        ),
        database=database,
        cache=cache,
    )
