"""Explicit strategy framework errors."""


class StrategyFrameworkError(RuntimeError):
    """Base exception for strategy plugin registration and lifecycle failures."""


class DuplicateStrategyError(StrategyFrameworkError):
    """Raised when two plugins claim the same strategy name."""


class StrategyLifecycleError(StrategyFrameworkError):
    """Raised when dispatch is attempted before successful initialization."""
