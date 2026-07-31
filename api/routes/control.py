"""Operator configuration APIs used by the local dashboard."""

# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_container
from control_plane.types import (
    RuntimeTradingConfiguration,
    TradingConfigurationAudit,
    TradingConfigurationUpdate,
)
from services.container import ApplicationContainer

router = APIRouter(prefix="/control", tags=["control-plane"])


@router.get("", response_model=RuntimeTradingConfiguration)
async def get_configuration(
    container: ApplicationContainer = Depends(get_container),
) -> RuntimeTradingConfiguration:
    """Return the active, secret-free operator configuration."""
    return await container.trading_controls.get()


@router.put("", response_model=RuntimeTradingConfiguration)
async def update_configuration(
    update: TradingConfigurationUpdate,
    container: ApplicationContainer = Depends(get_container),
) -> RuntimeTradingConfiguration:
    """Validate, audit, and apply an optimistic-concurrency dashboard update."""
    try:
        configuration = await container.trading_controls.update(update)
    except ValueError as error:
        status_code = (
            status.HTTP_409_CONFLICT
            if "version conflict" in str(error)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    await container.live_hub.publish(
        "control", "configuration_updated", configuration.model_dump(mode="json")
    )
    return configuration


@router.get("/audit", response_model=list[TradingConfigurationAudit])
async def configuration_audit(
    limit: int = 50, container: ApplicationContainer = Depends(get_container)
) -> list[TradingConfigurationAudit]:
    """List configuration versions for operator review and incident investigation."""
    return list(await container.trading_controls.list_audit(limit))


@router.get("/strategies")
async def available_strategies() -> list[dict[str, object]]:
    """Describe selectable strategy plugins without coupling the dashboard to code internals."""
    return [
        {
            "name": "ema_crossover",
            "label": "EMA Crossover",
            "description": "Completed-candle trend crossover with ATR risk sizing.",
            "parameters": [
                "interval",
                "fast_period",
                "slow_period",
                "base_confidence",
                "confidence_sensitivity",
                "max_confidence",
            ],
        }
    ]
