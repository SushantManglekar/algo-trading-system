"""Operational health and metrics endpoints."""

# ruff: noqa: B008

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST

from api.dependencies import get_container
from services.container import ApplicationContainer

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(container: ApplicationContainer = Depends(get_container)) -> dict[str, str]:
    """Return process liveness; use ``/ready`` for dependency readiness."""
    return {"status": "ok" if container.started else "starting"}


@router.get("/ready")
async def ready(container: ApplicationContainer = Depends(get_container)) -> JSONResponse:
    """Report whether enabled dependencies are able to serve production traffic."""
    readiness = await container.readiness()
    return JSONResponse(
        status_code=status.HTTP_200_OK if readiness["ready"] else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=readiness,
    )


@router.get("/metrics", include_in_schema=False)
async def metrics(container: ApplicationContainer = Depends(get_container)) -> Response:
    """Render application-scoped Prometheus metrics."""
    return Response(content=container.metrics.render(), media_type=CONTENT_TYPE_LATEST)
