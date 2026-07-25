from decimal import Decimal

from fastapi.testclient import TestClient

from api.app import create_app
from config.settings import AppSettings
from services.container import build_container


def test_api_preserves_request_id_and_returns_validation_errors() -> None:
    application = create_app(
        build_container(
            AppSettings(
                _env_file=None,
                analytics_starting_equity=Decimal(10_000),
                tick_buffer_per_symbol=100,
                candle_buffer_per_series=100,
            )
        )
    )

    with TestClient(application) as client:
        health = client.get("/health", headers={"X-Request-ID": "test-request-123"})
        assert health.status_code == 200
        assert health.headers["X-Request-ID"] == "test-request-123"

        invalid_tick = client.post("/market/ticks", json={"symbol": "AAPL"})
        assert invalid_tick.status_code == 422
        assert client.get("/market/ticks/latest/UNKNOWN").status_code == 404
