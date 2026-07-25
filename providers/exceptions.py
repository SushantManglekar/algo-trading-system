"""Provider lifecycle errors that callers can handle without vendor coupling."""


class MarketDataProviderError(RuntimeError):
    """Base error raised by a market-data provider adapter."""


class ProviderNotConnectedError(MarketDataProviderError):
    """Raised when an operation requires an active provider connection."""
