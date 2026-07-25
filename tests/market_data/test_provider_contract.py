from collections.abc import AsyncIterator, Sequence

import pytest

from market_data.provider import MarketDataProvider
from market_data.types import Candle, HistoricalCandleRequest, MarketTick


class StubMarketDataProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.connected = False
        self.symbols: set[str] = set()

    @property
    def name(self) -> str:
        return "stub"

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def subscribe(self, symbols: Sequence[str]) -> None:
        self.symbols.update(symbol.upper() for symbol in symbols)

    async def unsubscribe(self, symbols: Sequence[str]) -> None:
        self.symbols.difference_update(symbol.upper() for symbol in symbols)

    async def get_historical_candles(
        self, request: HistoricalCandleRequest
    ) -> Sequence[Candle]:
        return ()

    async def stream_ticks(self) -> AsyncIterator[MarketTick]:
        if False:
            yield MarketTick.model_construct()


@pytest.mark.asyncio
async def test_provider_contract_supports_explicit_lifecycle() -> None:
    provider = StubMarketDataProvider()

    await provider.connect()
    await provider.subscribe(["aapl", "msft"])
    await provider.unsubscribe(["MSFT"])
    await provider.disconnect()

    assert provider.name == "stub"
    assert provider.connected is False
    assert provider.symbols == {"AAPL"}


def test_incomplete_provider_cannot_be_instantiated() -> None:
    class IncompleteProvider(MarketDataProvider):
        @property
        def name(self) -> str:
            return "incomplete"

    with pytest.raises(TypeError, match="abstract"):
        IncompleteProvider()
