"""FastAPI application factory and lifespan integration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import market, signals, system
from services.container import ApplicationContainer, build_container


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    """Create a fully isolated ASGI application instance with explicit dependencies."""
    resolved_container = container or build_container()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await resolved_container.start()
        try:
            yield
        finally:
            await resolved_container.stop()

    app = FastAPI(title=resolved_container.settings.app_name, lifespan=lifespan)
    app.state.container = resolved_container
    app.include_router(system.router)
    app.include_router(market.router)
    app.include_router(signals.router)
    return app


app = create_app()
