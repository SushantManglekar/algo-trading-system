from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from analytics.engine import AnalyticsEngine
from analytics.types import AnalyticsSettings, ClosedSignalOutcome
from risk.types import RiskManagedSignal
from strategies.types import StrategyDirection


def managed_signal(timestamp: datetime) -> RiskManagedSignal:
    return RiskManagedSignal(
        symbol="AAPL",
        timestamp=timestamp,
        strategy="ema_2_3",
        direction=StrategyDirection.BUY,
        entry_price=Decimal(100),
        stop_loss=Decimal(98),
        take_profit=Decimal(104),
        atr_stop_loss=Decimal(98),
        trailing_stop_distance=Decimal(1),
        risk_reward=Decimal(2),
        position_size=10,
        position_risk=Decimal(20),
        expected_move=Decimal(4),
        confidence=Decimal("0.75"),
        reason="test signal",
    )


def settings() -> AnalyticsSettings:
    return AnalyticsSettings(
        starting_equity=Decimal(1000),
        reporting_timezone="America/New_York",
        risk_free_return_per_trade=Decimal(0),
    )


@pytest.mark.asyncio
async def test_analytics_engine_calculates_realized_performance_and_periods() -> None:
    engine = AnalyticsEngine(settings())
    first_open = datetime(2026, 7, 24, 14, 0, tzinfo=UTC)
    second_open = datetime(2026, 7, 24, 22, 30, tzinfo=UTC)
    await engine.record_outcome(
        ClosedSignalOutcome(
            signal=managed_signal(first_open),
            exit_price=Decimal(102),
            closed_at=first_open + timedelta(hours=1),
        )
    )
    await engine.record_outcome(
        ClosedSignalOutcome(
            signal=managed_signal(second_open),
            exit_price=Decimal(99),
            closed_at=second_open + timedelta(hours=2),
        )
    )

    snapshot = await engine.snapshot()
    overall = snapshot.overall

    assert overall.total_signals == 2
    assert overall.winning_signals == 1
    assert overall.losing_signals == 1
    assert overall.win_rate == Decimal("0.5")
    assert overall.average_gain == Decimal(20)
    assert overall.average_loss == Decimal(10)
    assert overall.profit_factor == Decimal(2)
    assert overall.expectancy == Decimal(5)
    assert overall.average_r_multiple == Decimal("0.25")
    assert overall.average_holding_seconds == Decimal(5400)
    assert overall.maximum_drawdown == Decimal(10)
    assert overall.maximum_drawdown_fraction == Decimal(10) / Decimal(1020)
    assert overall.sharpe_ratio is not None
    assert [period.period for period in snapshot.daily] == ["2026-07-24"]
    assert len(snapshot.weekly) == 1
    assert len(snapshot.monthly) == 1


@pytest.mark.asyncio
async def test_analytics_engine_rejects_duplicate_outcomes() -> None:
    engine = AnalyticsEngine(settings())
    opened_at = datetime(2026, 7, 24, 14, 0, tzinfo=UTC)
    outcome = ClosedSignalOutcome(
        signal=managed_signal(opened_at),
        exit_price=Decimal(102),
        closed_at=opened_at + timedelta(hours=1),
    )
    await engine.record_outcome(outcome)

    with pytest.raises(ValueError, match="already been recorded"):
        await engine.record_outcome(outcome)


def test_outcome_rejects_future_leakage_and_non_directional_signals() -> None:
    opened_at = datetime(2026, 7, 24, 14, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="cannot precede"):
        ClosedSignalOutcome(
            signal=managed_signal(opened_at),
            exit_price=Decimal(102),
            closed_at=opened_at - timedelta(seconds=1),
        )
