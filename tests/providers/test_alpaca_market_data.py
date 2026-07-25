from datetime import UTC, datetime, timedelta

import pytest

from config.settings import AppSettings, ProviderName
from market_data.types import CandleInterval, HistoricalCandleRequest
from providers.alpaca_market_data import AlpacaMarketDataProvider


class EmptyBarSet:
    """Represents Alpaca's empty response for an unavailable symbol."""

    def __getitem__(self, symbol: str) -> object:
        raise KeyError(f"No key {symbol} was found.")


class EmptyHistoryClient:
    """Avoids network access while exercising the vendor adapter boundary."""

    def get_stock_bars(self, request: object) -> EmptyBarSet:
        return EmptyBarSet()


@pytest.mark.asyncio
async def test_alpaca_history_returns_empty_sequence_when_symbol_has_no_bars() -> None:
    provider = AlpacaMarketDataProvider(
        AppSettings(
            _env_file=None,
            market_data_provider=ProviderName.ALPACA,
            alpaca_api_key="test-key",
            alpaca_api_secret="test-secret",
        )
    )
    provider._history = EmptyHistoryClient()  # type: ignore[assignment]
    await provider.connect()
    start_at = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)

    candles = await provider.get_historical_candles(
        HistoricalCandleRequest(
            symbol="ZZZZ",
            interval=CandleInterval.ONE_MINUTE,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=1),
        )
    )

    assert candles == ()
