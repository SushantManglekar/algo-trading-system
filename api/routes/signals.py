"""Signal-generation, history, and analytics REST endpoints."""

# ruff: noqa: B008

from fastapi import APIRouter, Depends, status

from analytics.types import AnalyticsSnapshot, ClosedSignalOutcome
from api.dependencies import get_container
from risk.types import RiskManagedSignal
from schemas.api import GenerateSignalRequest, GenerateSignalResponse, RecordOutcomeResponse
from services.container import ApplicationContainer

router = APIRouter(tags=["signals", "analytics"])


@router.post("/signals/generate", response_model=GenerateSignalResponse)
async def generate_signal(
    request: GenerateSignalRequest, container: ApplicationContainer = Depends(get_container)
) -> GenerateSignalResponse:
    """Apply all configured risk controls to one strategy intent."""
    decision = container.risk_engine.evaluate(request.intent, request.risk_context)
    container.metrics.signals_generated.labels(status=decision.status.value).inc()
    if decision.signal is not None:
        await container.signal_store.append(decision.signal)
    return GenerateSignalResponse(decision=decision)


@router.get("/signals", response_model=list[RiskManagedSignal])
async def signal_history(
    symbol: str | None = None, container: ApplicationContainer = Depends(get_container)
) -> list[RiskManagedSignal]:
    """Return generated risk-managed signal proposals, optionally filtered by symbol."""
    return list(await container.signal_store.list_signals(symbol))


@router.post("/analytics/outcomes", response_model=RecordOutcomeResponse, status_code=status.HTTP_201_CREATED)
async def record_outcome(
    outcome: ClosedSignalOutcome, container: ApplicationContainer = Depends(get_container)
) -> RecordOutcomeResponse:
    """Record an observed close for realized signal analytics; no orders are placed."""
    await container.analytics_engine.record_outcome(outcome)
    return RecordOutcomeResponse(outcome=outcome)


@router.get("/analytics", response_model=AnalyticsSnapshot)
async def analytics_dashboard(
    container: ApplicationContainer = Depends(get_container),
) -> AnalyticsSnapshot:
    """Return current realized performance analytics."""
    return await container.analytics_engine.snapshot()
