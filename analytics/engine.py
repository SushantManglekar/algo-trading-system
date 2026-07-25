"""Concurrency-safe calculation of realized signal performance analytics."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from statistics import mean
from zoneinfo import ZoneInfo

from analytics.types import (
    AnalyticsSettings,
    AnalyticsSnapshot,
    ClosedSignalOutcome,
    PerformanceStatistics,
    PeriodStatistics,
)


class AnalyticsEngine:
    """Accumulates only explicit closed outcomes; no forward-filled or simulated results."""

    def __init__(self, settings: AnalyticsSettings) -> None:
        self._settings = settings
        self._timezone = ZoneInfo(settings.reporting_timezone)
        self._outcomes: list[ClosedSignalOutcome] = []
        self._outcome_ids: set[str] = set()
        self._lock = asyncio.Lock()

    async def record_outcome(self, outcome: ClosedSignalOutcome) -> None:
        """Record one unique closed outcome for later aggregate reporting."""
        async with self._lock:
            outcome_id = str(outcome.outcome_id)
            if outcome_id in self._outcome_ids:
                raise ValueError("outcome has already been recorded")
            self._outcomes.append(outcome)
            self._outcome_ids.add(outcome_id)

    async def snapshot(self) -> AnalyticsSnapshot:
        """Return a point-in-time snapshot over all outcomes recorded so far."""
        async with self._lock:
            outcomes = tuple(sorted(self._outcomes, key=lambda item: item.closed_at))
        return AnalyticsSnapshot(
            overall=self._statistics(outcomes),
            daily=self._period_statistics(outcomes, self._daily_key),
            weekly=self._period_statistics(outcomes, self._weekly_key),
            monthly=self._period_statistics(outcomes, self._monthly_key),
        )

    def _statistics(self, outcomes: tuple[ClosedSignalOutcome, ...]) -> PerformanceStatistics:
        gains = [outcome.realized_pnl for outcome in outcomes if outcome.realized_pnl > Decimal(0)]
        losses = [outcome.realized_pnl for outcome in outcomes if outcome.realized_pnl < Decimal(0)]
        resolved = len(gains) + len(losses)
        gross_gain = sum(gains, Decimal(0))
        gross_loss = abs(sum(losses, Decimal(0)))
        maximum_drawdown, maximum_drawdown_fraction = self._maximum_drawdown(outcomes)
        return PerformanceStatistics(
            total_signals=len(outcomes),
            winning_signals=len(gains),
            losing_signals=len(losses),
            win_rate=Decimal(len(gains)) / resolved if resolved else None,
            average_gain=mean(gains) if gains else None,
            average_loss=abs(mean(losses)) if losses else None,
            profit_factor=gross_gain / gross_loss if gross_loss else None,
            sharpe_ratio=self._trade_sharpe(outcomes),
            expectancy=mean([outcome.realized_pnl for outcome in outcomes]) if outcomes else None,
            average_holding_seconds=(
                mean([outcome.holding_seconds for outcome in outcomes]) if outcomes else None
            ),
            maximum_drawdown=maximum_drawdown,
            maximum_drawdown_fraction=maximum_drawdown_fraction,
            average_r_multiple=mean([outcome.r_multiple for outcome in outcomes]) if outcomes else None,
        )

    def _trade_sharpe(self, outcomes: tuple[ClosedSignalOutcome, ...]) -> Decimal | None:
        if len(outcomes) < 2:
            return None
        excess_returns = [
            outcome.r_multiple - self._settings.risk_free_return_per_trade for outcome in outcomes
        ]
        average_return = mean(excess_returns)
        variance = sum((value - average_return) ** 2 for value in excess_returns) / Decimal(
            len(excess_returns) - 1
        )
        if variance == Decimal(0):
            return None
        return average_return / variance.sqrt()

    def _maximum_drawdown(self, outcomes: tuple[ClosedSignalOutcome, ...]) -> tuple[Decimal, Decimal]:
        equity = self._settings.starting_equity
        peak = equity
        max_drawdown = Decimal(0)
        max_fraction = Decimal(0)
        for outcome in outcomes:
            equity += outcome.realized_pnl
            peak = max(peak, equity)
            drawdown = peak - equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_fraction = drawdown / peak
        return max_drawdown, max_fraction

    def _period_statistics(
        self,
        outcomes: tuple[ClosedSignalOutcome, ...],
        period_key: Callable[[ClosedSignalOutcome], str],
    ) -> tuple[PeriodStatistics, ...]:
        grouped: dict[str, list[ClosedSignalOutcome]] = defaultdict(list)
        for outcome in outcomes:
            grouped[period_key(outcome)].append(outcome)
        return tuple(
            PeriodStatistics(period=period, statistics=self._statistics(tuple(grouped[period])))
            for period in sorted(grouped)
        )

    def _daily_key(self, outcome: ClosedSignalOutcome) -> str:
        return outcome.closed_at.astimezone(self._timezone).date().isoformat()

    def _weekly_key(self, outcome: ClosedSignalOutcome) -> str:
        local_time = outcome.closed_at.astimezone(self._timezone)
        iso_year, iso_week, _ = local_time.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    def _monthly_key(self, outcome: ClosedSignalOutcome) -> str:
        return outcome.closed_at.astimezone(self._timezone).strftime("%Y-%m")
