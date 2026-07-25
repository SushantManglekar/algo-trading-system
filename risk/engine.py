"""Strict, deterministic risk evaluation and trailing-stop calculations."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from risk.types import (
    RiskContext,
    RiskDecision,
    RiskDecisionStatus,
    RiskManagedSignal,
    RiskPolicy,
)
from strategies.types import StrategyDirection, StrategySignalIntent


class TrailingStopCalculator:
    """Moves stops only in a favorable direction; it never widens existing risk."""

    @staticmethod
    def next_stop(
        direction: StrategyDirection,
        current_stop: Decimal,
        favorable_extreme: Decimal,
        atr: Decimal,
        trailing_atr_multiple: Decimal,
    ) -> Decimal:
        distance = atr * trailing_atr_multiple
        if direction is StrategyDirection.BUY:
            return max(current_stop, favorable_extreme - distance)
        if direction is StrategyDirection.SELL:
            return min(current_stop, favorable_extreme + distance)
        raise ValueError("trailing stops apply only to BUY or SELL signals")


class RiskEngine:
    """Converts directional strategy intent into a constrained trade proposal."""

    def __init__(self, policy: RiskPolicy) -> None:
        self._policy = policy

    def evaluate(self, intent: StrategySignalIntent, context: RiskContext) -> RiskDecision:
        """Approve only entries that preserve configured account-level limits."""
        if intent.direction in {StrategyDirection.HOLD, StrategyDirection.EXIT}:
            return RiskDecision(
                status=RiskDecisionStatus.NOT_APPLICABLE,
                intent=intent,
                reason="direction_does_not_open_a_position",
            )
        if context.would_average_down:
            return self._rejected(intent, "averaging_down_is_prohibited")
        if context.consecutive_losses >= self._policy.max_consecutive_losses:
            return self._rejected(intent, "maximum_consecutive_losses_reached")

        stop_distance = context.atr * self._policy.stop_atr_multiple
        expected_move = context.atr * self._policy.target_atr_multiple
        if intent.direction is StrategyDirection.BUY:
            stop_loss = context.entry_price - stop_distance
            take_profit = context.entry_price + expected_move
        else:
            stop_loss = context.entry_price + stop_distance
            take_profit = context.entry_price - expected_move
        if stop_loss <= Decimal(0) or take_profit <= Decimal(0):
            return self._rejected(intent, "computed_price_is_not_positive")

        maximum_position_risk = context.account_equity * self._policy.risk_per_trade_fraction
        position_size = int((maximum_position_risk / stop_distance).to_integral_value(ROUND_DOWN))
        if position_size < 1:
            return self._rejected(intent, "account_risk_limit_cannot_fund_one_share")
        position_risk = Decimal(position_size) * stop_distance
        maximum_daily_loss = context.account_equity * self._policy.max_daily_loss_fraction
        current_daily_loss = max(Decimal(0), -context.daily_realized_pnl)
        if current_daily_loss + position_risk > maximum_daily_loss:
            return self._rejected(intent, "maximum_daily_loss_would_be_exceeded")

        risk_reward = expected_move / stop_distance
        signal = RiskManagedSignal(
            symbol=intent.symbol,
            timestamp=intent.timestamp,
            strategy=intent.strategy,
            direction=intent.direction,
            entry_price=context.entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_stop_loss=stop_loss,
            trailing_stop_distance=context.atr * self._policy.trailing_stop_atr_multiple,
            risk_reward=risk_reward.quantize(Decimal("0.001")),
            position_size=position_size,
            position_risk=position_risk,
            expected_move=expected_move,
            confidence=intent.confidence,
            reason=intent.reason,
        )
        return RiskDecision(
            status=RiskDecisionStatus.APPROVED,
            intent=intent,
            signal=signal,
        )

    @staticmethod
    def _rejected(intent: StrategySignalIntent, reason: str) -> RiskDecision:
        return RiskDecision(status=RiskDecisionStatus.REJECTED, intent=intent, reason=reason)
