from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from risk.engine import RiskEngine, TrailingStopCalculator
from risk.types import RiskContext, RiskDecisionStatus, RiskPolicy
from strategies.types import StrategyDirection, StrategySignalIntent


def policy() -> RiskPolicy:
    return RiskPolicy(
        risk_per_trade_fraction=Decimal("0.01"),
        max_daily_loss_fraction=Decimal("0.02"),
        max_consecutive_losses=3,
        stop_atr_multiple=Decimal("1.5"),
        target_atr_multiple=Decimal(3),
        trailing_stop_atr_multiple=Decimal(1),
        minimum_risk_reward=Decimal(2),
    )


def intent(direction: StrategyDirection = StrategyDirection.BUY) -> StrategySignalIntent:
    return StrategySignalIntent(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 24, 14, 0, tzinfo=UTC),
        strategy="ema_2_3",
        direction=direction,
        confidence=Decimal("0.75"),
        reason="completed candle crossover",
    )


def context(**overrides: object) -> RiskContext:
    values: dict[str, object] = {
        "entry_price": Decimal(100),
        "atr": Decimal(2),
        "account_equity": Decimal(10_000),
        "daily_realized_pnl": Decimal(-50),
        "consecutive_losses": 0,
    }
    values.update(overrides)
    return RiskContext(**values)


def test_risk_engine_sizes_long_signal_with_atr_stop_and_target() -> None:
    decision = RiskEngine(policy()).evaluate(intent(), context())

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.signal is not None
    assert decision.signal.stop_loss == Decimal(97)
    assert decision.signal.take_profit == Decimal(106)
    assert decision.signal.atr_stop_loss == Decimal(97)
    assert decision.signal.trailing_stop_distance == Decimal(2)
    assert decision.signal.risk_reward == Decimal(2)
    assert decision.signal.position_size == 33
    assert decision.signal.position_risk == Decimal(99)


def test_risk_engine_sizes_short_signal_symmetrically() -> None:
    decision = RiskEngine(policy()).evaluate(intent(StrategyDirection.SELL), context())

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.signal is not None
    assert decision.signal.stop_loss == Decimal(103)
    assert decision.signal.take_profit == Decimal(94)


@pytest.mark.parametrize(
    ("context_override", "reason"),
    [
        ({"would_average_down": True}, "averaging_down_is_prohibited"),
        ({"consecutive_losses": 3}, "maximum_consecutive_losses_reached"),
        ({"daily_realized_pnl": Decimal(-150)}, "maximum_daily_loss_would_be_exceeded"),
    ],
)
def test_risk_engine_blocks_capital_preservation_violations(
    context_override: dict[str, object], reason: str
) -> None:
    decision = RiskEngine(policy()).evaluate(intent(), context(**context_override))

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.signal is None
    assert decision.reason == reason


def test_non_entry_intents_do_not_create_a_trade_proposal() -> None:
    decision = RiskEngine(policy()).evaluate(intent(StrategyDirection.HOLD), context())

    assert decision.status is RiskDecisionStatus.NOT_APPLICABLE
    assert decision.reason == "direction_does_not_open_a_position"


def test_trailing_stop_only_tightens_risk() -> None:
    assert TrailingStopCalculator.next_stop(
        StrategyDirection.BUY, Decimal(97), Decimal(105), Decimal(2), Decimal(1)
    ) == Decimal(103)
    assert TrailingStopCalculator.next_stop(
        StrategyDirection.BUY, Decimal(103), Decimal(104), Decimal(2), Decimal(1)
    ) == Decimal(103)
    assert TrailingStopCalculator.next_stop(
        StrategyDirection.SELL, Decimal(103), Decimal(95), Decimal(2), Decimal(1)
    ) == Decimal(97)


def test_risk_policy_rejects_insufficient_target_reward() -> None:
    with pytest.raises(ValidationError, match="minimum risk-reward"):
        RiskPolicy(
            risk_per_trade_fraction=Decimal("0.01"),
            max_daily_loss_fraction=Decimal("0.02"),
            max_consecutive_losses=3,
            stop_atr_multiple=Decimal(2),
            target_atr_multiple=Decimal(3),
            trailing_stop_atr_multiple=Decimal(1),
            minimum_risk_reward=Decimal(2),
        )
