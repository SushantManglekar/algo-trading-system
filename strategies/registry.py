"""Registry of independently constructed strategy plugins."""

from __future__ import annotations

from strategies.contracts import Strategy
from strategies.exceptions import DuplicateStrategyError


class StrategyRegistry:
    """Owns plugin identity without constructing strategies or sharing their state."""

    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        name = strategy.name.strip()
        if not name:
            raise ValueError("strategy name cannot be blank")
        if name in self._strategies:
            raise DuplicateStrategyError(f"strategy '{name}' is already registered")
        self._strategies[name] = strategy

    def all(self) -> tuple[Strategy, ...]:
        """Return strategies in registration order for deterministic processing."""
        return tuple(self._strategies.values())
