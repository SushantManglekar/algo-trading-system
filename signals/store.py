"""In-memory signal-history adapter used until database repositories are introduced."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from risk.types import RiskManagedSignal


class InMemorySignalStore:
    """Stores generated risk-managed signal proposals in insertion order."""

    def __init__(self) -> None:
        self._signals: list[RiskManagedSignal] = []
        self._lock = asyncio.Lock()

    async def append(self, signal: RiskManagedSignal) -> None:
        async with self._lock:
            self._signals.append(signal)

    async def list_signals(self, symbol: str | None = None) -> Sequence[RiskManagedSignal]:
        async with self._lock:
            signals = tuple(self._signals)
        return tuple(signal for signal in signals if symbol is None or signal.symbol == symbol.upper())
