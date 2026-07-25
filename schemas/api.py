"""HTTP request and response schemas that compose domain objects without duplication."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from analytics.types import ClosedSignalOutcome
from risk.types import RiskContext, RiskDecision
from strategies.types import StrategySignalIntent


class TickIngestResponse(BaseModel):
    """Result of validating, storing, and candle-aggregating one submitted tick."""

    model_config = ConfigDict(frozen=True)

    accepted: bool
    reason: str | None = None
    updated_candle_count: int = 0
    completed_candle_count: int = 0


class GenerateSignalRequest(BaseModel):
    """A strategy intent plus point-in-time context for risk evaluation."""

    model_config = ConfigDict(frozen=True)

    intent: StrategySignalIntent
    risk_context: RiskContext


class GenerateSignalResponse(BaseModel):
    """Risk decision returned from the signal-generation endpoint."""

    model_config = ConfigDict(frozen=True)

    decision: RiskDecision


class RecordOutcomeResponse(BaseModel):
    """Acknowledgement for one analytics outcome record."""

    model_config = ConfigDict(frozen=True)

    outcome: ClosedSignalOutcome
