from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from api.app import create_app
from config.settings import AppSettings
from services.container import build_container


def test_rest_api_runs_end_to_end_with_in_memory_dependencies() -> None:
    settings = AppSettings(
        analytics_starting_equity=Decimal(10_000),
        tick_buffer_per_symbol=100,
        candle_buffer_per_series=100,
    )
    application = create_app(build_container(settings))
    timestamp = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    tick_payload = {
        "timestamp": timestamp.isoformat(),
        "received_at": (timestamp + timedelta(milliseconds=2)).isoformat(),
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "price": "200.00",
        "bid": "199.99",
        "ask": "200.01",
        "volume": "1000",
        "trade_size": "100",
    }
    intent = {
        "symbol": "AAPL",
        "timestamp": timestamp.isoformat(),
        "strategy": "ema_2_3",
        "direction": "BUY",
        "confidence": "0.75",
        "reason": "completed candle crossover",
    }
    risk_context = {
        "entry_price": "200.00",
        "atr": "2.00",
        "account_equity": "10000.00",
        "daily_realized_pnl": "0",
        "consecutive_losses": 0,
    }

    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/market/status").json()["connected"] is True
        assert client.get("/trading/status").json()["mode"] == "paper"
        assert client.get("/trading/account").json()["equity"] == "100000"
        assert client.get("/trading/positions").json() == []
        assert client.get("/trading/orders").json() == []

        ingestion = client.post("/market/ticks", json=tick_payload)
        assert ingestion.status_code == 202
        assert ingestion.json()["accepted"] is True
        assert client.get("/market/ticks/latest/AAPL").json()["symbol"] == "AAPL"
        latest_candle = client.get("/market/candles/latest/AAPL", params={"interval": "1m"})
        assert latest_candle.status_code == 200
        assert latest_candle.json()["is_complete"] is False

        generated = client.post(
            "/signals/generate", json={"intent": intent, "risk_context": risk_context}
        )
        assert generated.status_code == 200
        decision = generated.json()["decision"]
        assert decision["status"] == "approved"
        assert len(client.get("/signals", params={"symbol": "AAPL"}).json()) == 1

        outcome_payload = {
            "signal": decision["signal"],
            "exit_price": "204.00",
            "closed_at": (timestamp + timedelta(hours=1)).isoformat(),
        }
        recorded = client.post("/analytics/outcomes", json=outcome_payload)
        assert recorded.status_code == 201
        analytics = client.get("/analytics")
        assert analytics.status_code == 200
        assert analytics.json()["overall"]["total_signals"] == 1
        assert b"trading_ticks_ingested_total" in client.get("/metrics").content
