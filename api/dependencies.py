"""FastAPI dependency providers."""

from fastapi import Request

from services.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    """Resolve dependencies from the current application instance, not global state."""
    return request.app.state.container
