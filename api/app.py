"""FastAPI application factory and lifespan integration."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import control, live, market, signals, system, trading
from core.logging import configure_json_logging
from services.container import ApplicationContainer, build_container

logger = logging.getLogger(__name__)


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    """Create a fully isolated ASGI application instance with explicit dependencies."""
    resolved_container = container or build_container()
    configure_json_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await resolved_container.start()
        try:
            yield
        finally:
            await resolved_container.stop()

    app = FastAPI(title=resolved_container.settings.app_name, lifespan=lifespan)
    app.state.container = resolved_container
    dashboard_directory = Path(__file__).parent / "dashboard"
    app.mount("/assets", StaticFiles(directory=dashboard_directory), name="dashboard-assets")

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        """Serve the local operator dashboard from the same origin as the API."""
        return FileResponse(dashboard_directory / "index.html")

    @app.middleware("http")
    async def request_correlation(request: Request, call_next: object) -> object:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        correlation_id = request.headers.get("X-Correlation-ID", request_id)
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        started_at = perf_counter()
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request_completed",
            extra={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1_000, 3),
            },
        )
        return response

    app.include_router(system.router)
    app.include_router(control.router)
    app.include_router(market.router)
    app.include_router(signals.router)
    app.include_router(trading.router)
    app.include_router(live.router)
    return app


app = create_app()
