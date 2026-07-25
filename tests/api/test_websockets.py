from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from api.app import create_app
from config.settings import AppSettings
from services.container import build_container


def test_websocket_topics_broadcast_rest_workflow_updates() -> None:
    application = create_app(
        build_container(
            AppSettings(
                analytics_starting_equity=Decimal(10_000),
                tick_buffer_per_symbol=100,
                candle_buffer_per_series=100,
            )
        )
    )
    timestamp = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    tick_payload = {
        "timestamp": timestamp.isoformat(),
        "received_at": (timestamp + timedelta(milliseconds=1)).isoformat(),
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "price": "200.00",
        "bid": "199.99",
        "ask": "200.01",
        "volume": "1000",
        "trade_size": "100",
    }
    request_payload = {
        "intent": {
            "symbol": "AAPL",
            "timestamp": timestamp.isoformat(),
            "strategy": "ema_2_3",
            "direction": "BUY",
            "confidence": "0.75",
            "reason": "completed candle crossover",
        },
        "risk_context": {
            "entry_price": "200.00",
            "atr": "2.00",
            "account_equity": "10000.00",
            "daily_realized_pnl": "0",
            "consecutive_losses": 0,
        },
    }

    with TestClient(application) as client:
        with client.websocket_connect("/ws/ticks") as ticks_socket, client.websocket_connect(
            "/ws/candles"
        ) as candles_socket:
            assert client.post("/market/ticks", json=tick_payload).status_code == 202
            tick_event = ticks_socket.receive_json()
            candle_event = candles_socket.receive_json()
            assert tick_event["event"] == "tick"
            assert tick_event["data"]["symbol"] == "AAPL"
            assert candle_event["event"] == "candle_updated"

        with client.websocket_connect("/ws/signals") as signals_socket:
            generated = client.post("/signals/generate", json=request_payload)
            decision = generated.json()["decision"]
            signal_event = signals_socket.receive_json()
            assert signal_event["event"] == "risk_decision"
            assert signal_event["data"]["status"] == "approved"

        with client.websocket_connect("/ws/analytics") as analytics_socket:
            outcome_payload = {
                "signal": decision["signal"],
                "exit_price": "204.00",
                "closed_at": (timestamp + timedelta(hours=1)).isoformat(),
            }
            assert client.post("/analytics/outcomes", json=outcome_payload).status_code == 201
            analytics_event = analytics_socket.receive_json()
            assert analytics_event["event"] == "analytics_updated"
            assert analytics_event["data"]["overall"]["total_signals"] == 1
