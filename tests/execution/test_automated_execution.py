from datetime import UTC, datetime
from decimal import Decimal

import pytest

from config.settings import AppSettings
from execution.in_memory import InMemoryExecutionAuditStore
from execution.service import AutomatedExecutionService
from providers.mock_broker import MockBrokerageProvider
from risk.types import RiskManagedSignal
from strategies.types import StrategyDirection


def signal() -> RiskManagedSignal:
    return RiskManagedSignal(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 25, 14, 0, tzinfo=UTC),
        strategy="ema_crossover",
        direction=StrategyDirection.BUY,
        entry_price=Decimal(100),
        stop_loss=Decimal(98),
        take_profit=Decimal(104),
        atr_stop_loss=Decimal(98),
        trailing_stop_distance=Decimal(1),
        risk_reward=Decimal(2),
        position_size=10,
        position_risk=Decimal(20),
        expected_move=Decimal(4),
        confidence=Decimal("0.75"),
        reason="test",
    )


@pytest.mark.asyncio
async def test_automated_execution_reserves_idempotency_before_submission() -> None:
    settings = AppSettings(
        _env_file=None,
        order_submission_enabled=True,
        automation_enabled=True,
        automation_confirmation="ENABLE_PAPER_AUTOMATION",
        symbols="AAPL",
    )
    audit = InMemoryExecutionAuditStore()
    service = AutomatedExecutionService(settings, MockBrokerageProvider(), audit)

    first = await service.execute_entry(signal())
    duplicate = await service.execute_entry(signal())

    assert first is not None
    assert first.client_order_id.startswith("ats-")
    assert duplicate is None
    assert len(audit.orders) == 1
