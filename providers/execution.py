"""Broker-neutral execution boundary; implementations must enforce their own safety policy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class ExecutionProvider(ABC):
    """Execution provider boundary kept separate from market-data ingestion."""

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        """Return whether this provider is attached to a paper account."""

    @abstractmethod
    async def submit_market_order(self, symbol: str, quantity: Decimal, side: OrderSide) -> str:
        """Submit a manually approved market order and return the broker order identifier."""
