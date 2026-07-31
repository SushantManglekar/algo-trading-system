"""Read-only backend views over broker account, positions, execution audit, and worker state."""

# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_container
from providers.execution import AccountSnapshot, ExecutionOrder, PositionSnapshot
from services.container import ApplicationContainer

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/status")
async def trading_status(container: ApplicationContainer = Depends(get_container)) -> dict[str, object]:
    """Expose effective trading mode and worker state without exposing credentials."""
    configuration = await container.trading_controls.get()
    return {
        "mode": configuration.mode,
        "automation_enabled": configuration.place_orders_automatically,
        "order_submission_enabled": configuration.place_orders_automatically,
        "monitoring_enabled": configuration.monitoring_enabled,
        "market_data_provider": container.provider.name,
        "execution_provider": container.settings.execution_provider,
        "pipeline_running": container.pipeline_worker.is_running,
        "symbols": configuration.symbols,
        "configuration_version": configuration.version,
    }


@router.get("/account", response_model=AccountSnapshot)
async def account(container: ApplicationContainer = Depends(get_container)) -> AccountSnapshot:
    """Fetch and durably snapshot current broker capital and daily mark-to-market P/L inputs."""
    account_snapshot, _ = await container.execution_service.portfolio()
    return account_snapshot


@router.get("/positions", response_model=list[PositionSnapshot])
async def positions(container: ApplicationContainer = Depends(get_container)) -> list[PositionSnapshot]:
    """Fetch and durably snapshot current broker holdings and unrealized P/L."""
    _, current_positions = await container.execution_service.portfolio()
    return list(current_positions)


@router.get("/orders", response_model=list[ExecutionOrder])
async def orders(container: ApplicationContainer = Depends(get_container)) -> list[ExecutionOrder]:
    """Return the application execution audit trail, including blocked/failed submissions."""
    return list(await container.execution_audit_store.list_orders())
