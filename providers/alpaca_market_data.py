"""Alpaca market-data adapter with a thread-safe async stream bridge."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from config.settings import AppSettings
from market_data.provider import MarketDataProvider
from market_data.types import Candle, CandleInterval, HistoricalCandleRequest, MarketTick
from providers.exceptions import ProviderNotConnectedError


class AlpacaMarketDataProvider(MarketDataProvider):
    """Streams trades only after a contemporaneous quote is known for each symbol."""

    def __init__(self, settings: AppSettings) -> None:
        if settings.market_data_provider != "alpaca":
            raise ValueError("Alpaca adapter requires market_data_provider=alpaca")
        if settings.alpaca_api_key is None or settings.alpaca_api_secret is None:
            raise ValueError("Alpaca API credentials are required")
        api_key = settings.alpaca_api_key.get_secret_value()
        secret = settings.alpaca_api_secret.get_secret_value()
        self._history = StockHistoricalDataClient(api_key, secret)
        self._stream = StockDataStream(api_key, secret)
        self._queue: asyncio.Queue[MarketTick | None] = asyncio.Queue()
        self._quotes: dict[str, tuple[Decimal, Decimal]] = {}
        self._subscriptions: set[str] = set()
        self._connected = False
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._runner: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "alpaca"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        async with self._lock:
            if self._connected:
                return
            self._queue = asyncio.Queue()
            self._main_loop = asyncio.get_running_loop()
            self._connected = True

    async def disconnect(self) -> None:
        async with self._lock:
            if not self._connected:
                return
            self._connected = False
            self._subscriptions.clear()
            await self._queue.put(None)
            runner, self._runner = self._runner, None
        if runner is not None:
            await asyncio.to_thread(self._stream.stop)
            await asyncio.gather(runner, return_exceptions=True)

    async def subscribe(self, symbols: Sequence[str]) -> None:
        normalized = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        if not normalized:
            raise ValueError("at least one non-blank symbol is required")
        async with self._lock:
            self._require_connected()
            new_symbols = tuple(sorted(normalized - self._subscriptions))
            if not new_symbols:
                return
            self._stream.subscribe_quotes(self._on_quote, *new_symbols)
            self._stream.subscribe_trades(self._on_trade, *new_symbols)
            self._subscriptions.update(new_symbols)
            if self._runner is None:
                self._runner = asyncio.create_task(self._run_stream(), name="alpaca-stock-data")

    async def unsubscribe(self, symbols: Sequence[str]) -> None:
        normalized = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        async with self._lock:
            self._require_connected()
            active = tuple(sorted(normalized & self._subscriptions))
            if active:
                self._stream.unsubscribe_quotes(*active)
                self._stream.unsubscribe_trades(*active)
                self._subscriptions.difference_update(active)
                for symbol in active:
                    self._quotes.pop(symbol, None)

    async def get_historical_candles(
        self, request: HistoricalCandleRequest
    ) -> Sequence[Candle]:
        self._require_connected()
        bars = await asyncio.to_thread(
            self._history.get_stock_bars,
            StockBarsRequest(
                symbol_or_symbols=request.symbol,
                start=request.start_at,
                end=request.end_at,
                timeframe=self._timeframe(request.interval),
            ),
        )
        return tuple(
            Candle(
                symbol=request.symbol,
                interval=request.interval,
                start_at=bar.timestamp.astimezone(UTC),
                end_at=self._bar_end(bar.timestamp, request.interval),
                open=Decimal(str(bar.open)),
                high=Decimal(str(bar.high)),
                low=Decimal(str(bar.low)),
                close=Decimal(str(bar.close)),
                volume=Decimal(str(bar.volume)),
                is_complete=True,
            )
            for bar in bars[request.symbol]
        )

    async def stream_ticks(self) -> AsyncIterator[MarketTick]:
        self._require_connected()
        while True:
            tick = await self._queue.get()
            if tick is None:
                return
            yield tick

    async def _run_stream(self) -> None:
        await asyncio.to_thread(self._stream.run)

    async def _on_quote(self, quote: object) -> None:
        symbol = str(getattr(quote, "symbol", "")).upper()
        if not symbol:
            return
        bid, ask = Decimal(str(quote.bid_price)), Decimal(str(quote.ask_price))
        if bid > Decimal(0) and ask >= bid:
            self._quotes[symbol] = (bid, ask)

    async def _on_trade(self, trade: object) -> None:
        symbol = str(getattr(trade, "symbol", "")).upper()
        quote = self._quotes.get(symbol)
        loop = self._main_loop
        if not symbol or quote is None or loop is None:
            return
        timestamp = getattr(trade, "timestamp", None)
        if not isinstance(timestamp, datetime):
            return
        tick = MarketTick(
            timestamp=timestamp.astimezone(UTC),
            received_at=datetime.now(UTC),
            symbol=symbol,
            exchange=str(getattr(trade, "exchange", "ALPACA")),
            price=Decimal(str(trade.price)),
            bid=quote[0],
            ask=quote[1],
            volume=Decimal(str(getattr(trade, "size", 0))),
            trade_size=Decimal(str(getattr(trade, "size", 0))),
            conditions=tuple(str(item) for item in (getattr(trade, "conditions", None) or ())),
        )
        asyncio.run_coroutine_threadsafe(self._queue.put(tick), loop)

    def _require_connected(self) -> None:
        if not self._connected:
            raise ProviderNotConnectedError("provider is not connected")

    @staticmethod
    def _timeframe(interval: CandleInterval) -> TimeFrame:
        mapping = {
            CandleInterval.ONE_MINUTE: (1, TimeFrameUnit.Minute),
            CandleInterval.TWO_MINUTES: (2, TimeFrameUnit.Minute),
            CandleInterval.THREE_MINUTES: (3, TimeFrameUnit.Minute),
            CandleInterval.FIVE_MINUTES: (5, TimeFrameUnit.Minute),
            CandleInterval.TEN_MINUTES: (10, TimeFrameUnit.Minute),
            CandleInterval.FIFTEEN_MINUTES: (15, TimeFrameUnit.Minute),
            CandleInterval.THIRTY_MINUTES: (30, TimeFrameUnit.Minute),
            CandleInterval.FORTY_FIVE_MINUTES: (45, TimeFrameUnit.Minute),
            CandleInterval.ONE_HOUR: (1, TimeFrameUnit.Hour),
            CandleInterval.TWO_HOURS: (2, TimeFrameUnit.Hour),
            CandleInterval.FOUR_HOURS: (4, TimeFrameUnit.Hour),
            CandleInterval.DAILY: (1, TimeFrameUnit.Day),
            CandleInterval.WEEKLY: (1, TimeFrameUnit.Week),
            CandleInterval.MONTHLY: (1, TimeFrameUnit.Month),
        }
        amount, unit = mapping[interval]
        return TimeFrame(amount, unit)

    @staticmethod
    def _bar_end(start_at: datetime, interval: CandleInterval) -> datetime:
        """Use the interval duration only for provider history; session aggregation remains calendar-aware."""
        seconds = {
            CandleInterval.ONE_MINUTE: 60,
            CandleInterval.TWO_MINUTES: 120,
            CandleInterval.THREE_MINUTES: 180,
            CandleInterval.FIVE_MINUTES: 300,
            CandleInterval.TEN_MINUTES: 600,
            CandleInterval.FIFTEEN_MINUTES: 900,
            CandleInterval.THIRTY_MINUTES: 1800,
            CandleInterval.FORTY_FIVE_MINUTES: 2700,
            CandleInterval.ONE_HOUR: 3600,
            CandleInterval.TWO_HOURS: 7200,
            CandleInterval.FOUR_HOURS: 14400,
        }
        from datetime import timedelta

        return start_at.astimezone(UTC) + timedelta(seconds=seconds.get(interval, 86_400))
