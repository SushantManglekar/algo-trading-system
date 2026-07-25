"""Persistence boundary for observed closed signal outcomes."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

from analytics.types import ClosedSignalOutcome


class OutcomeStore(Protocol):
    """Stores unique observed closes that feed the analytics engine."""

    async def append(self, outcome: ClosedSignalOutcome) -> None:
        """Persist one outcome or reject a duplicate outcome identifier."""

    async def list_outcomes(self) -> Sequence[ClosedSignalOutcome]:
        """Return outcomes in ascending close time."""


class InMemoryOutcomeStore:
    """Test/development implementation of the outcome persistence boundary."""

    def __init__(self) -> None:
        self._outcomes: list[ClosedSignalOutcome] = []
        self._outcome_ids: set[str] = set()
        self._lock = asyncio.Lock()

    async def append(self, outcome: ClosedSignalOutcome) -> None:
        async with self._lock:
            outcome_id = str(outcome.outcome_id)
            if outcome_id in self._outcome_ids:
                raise ValueError("outcome has already been recorded")
            self._outcomes.append(outcome)
            self._outcome_ids.add(outcome_id)

    async def list_outcomes(self) -> Sequence[ClosedSignalOutcome]:
        async with self._lock:
            return tuple(sorted(self._outcomes, key=lambda item: item.closed_at))
