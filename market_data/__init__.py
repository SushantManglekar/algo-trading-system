"""Market-data domain contracts and processing."""

from market_data.candle_engine import CandleEngine, CandleEngineSettings, CandleUpdate
from market_data.candle_history import (
    HistoricalCandleResult,
    HistoricalCandleService,
    HistoricalCandleSource,
)
from market_data.exchange_calendar import CandleBucket, XnysExchangeCalendar
from market_data.provider import MarketDataProvider
from market_data.tick_processor import (
    TickProcessingResult,
    TickProcessingStatus,
    TickProcessor,
    TickProcessorSettings,
)
from market_data.tick_store import InMemoryTickStore, TickStore
from market_data.types import Candle, CandleInterval, HistoricalCandleRequest, MarketTick

__all__ = [
    "Candle",
    "CandleBucket",
    "CandleEngine",
    "CandleEngineSettings",
    "CandleInterval",
    "CandleUpdate",
    "HistoricalCandleRequest",
    "HistoricalCandleResult",
    "HistoricalCandleService",
    "HistoricalCandleSource",
    "InMemoryTickStore",
    "MarketDataProvider",
    "MarketTick",
    "TickProcessingResult",
    "TickProcessingStatus",
    "TickProcessor",
    "TickProcessorSettings",
    "TickStore",
    "XnysExchangeCalendar",
]
