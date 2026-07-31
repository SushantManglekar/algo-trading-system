from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from config.settings import AppSettings
from services.container import build_container


def test_dashboard_and_control_plane_reconfigure_the_running_application() -> None:
    application = create_app(build_container(AppSettings(_env_file=None, symbols="AAPL")))

    with TestClient(application) as client:
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert 'id="root"' in dashboard.text
        assert "/assets/" in dashboard.text

        current = client.get("/control")
        assert current.status_code == 200
        configuration = current.json()
        assert configuration["symbols"] == ["AAPL"]

        configuration.update({"symbols": ["MSFT"], "monitoring_enabled": False})
        configuration.pop("version")
        configuration.pop("updated_at")
        configuration["expected_version"] = 1
        updated = client.put("/control", json=configuration)
        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        assert updated.json()["symbols"] == ["MSFT"]

        status = client.get("/trading/status").json()
        assert status["symbols"] == ["MSFT"]
        assert status["monitoring_enabled"] is False
        assert status["pipeline_running"] is False
        assert [entry["version"] for entry in client.get("/control/audit").json()] == [2, 1]
