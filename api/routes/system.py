"""Operational health and metrics endpoints."""

# ruff: noqa: B008

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST

from api.dependencies import get_container
from services.container import ApplicationContainer

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(container: ApplicationContainer = Depends(get_container)) -> dict[str, str]:
    """Return liveness and provider-connection health for orchestration systems."""
    return {"status": "ok" if container.started else "starting"}


@router.get("/metrics", include_in_schema=False)
async def metrics(container: ApplicationContainer = Depends(get_container)) -> Response:
    """Render application-scoped Prometheus metrics."""
    return Response(content=container.metrics.render(), media_type=CONTENT_TYPE_LATEST)
