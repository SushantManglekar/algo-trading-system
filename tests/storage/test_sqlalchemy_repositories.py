from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics.engine import AnalyticsEngine
from analytics.types import AnalyticsSettings, ClosedSignalOutcome
from config.settings import AppSettings
from control_plane.repository import SqlAlchemyTradingControlStore
from control_plane.service import TradingControlService
from market_data.types import Candle, CandleInterval, MarketTick
from models import CandleRecord, SignalOutcomeRecord, SignalRecord, TickRecord
from providers.execution import (
    AccountSnapshot,
    ExecutionOrder,
    OrderLifecycleStatus,
    OrderRequest,
    OrderSide,
)
from repositories.candle_repository import SqlAlchemyCandleStore
from repositories.execution_repository import SqlAlchemyExecutionRepository
from repositories.outcome_repository import SqlAlchemyOutcomeStore
from repositories.signal_repository import SqlAlchemySignalStore
from repositories.tick_repository import SqlAlchemyTickStore
from risk.types import RiskManagedSignal
from storage.database import Base, Database
from strategies.types import StrategyDirection


@pytest.fixture
async def sessions() -> async_sessionmaker[AsyncSession]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield database.sessions
    finally:
        await database.dispose()


def tick(at: datetime) -> MarketTick:
    return MarketTick(
        timestamp=at,
        received_at=at + timedelta(milliseconds=3),
        symbol="aapl",
        exchange="nasdaq",
        price=Decimal("200.00"),
        bid=Decimal("199.99"),
        ask=Decimal("200.01"),
        volume=Decimal(1000),
        trade_size=Decimal(100),
        conditions=("@", "I"),
    )


def signal(at: datetime) -> RiskManagedSignal:
    return RiskManagedSignal(
        symbol="AAPL",
        timestamp=at,
        strategy="ema_2_3",
        direction=StrategyDirection.BUY,
        entry_price=Decimal(200),
        stop_loss=Decimal(198),
        take_profit=Decimal(204),
        atr_stop_loss=Decimal(198),
        trailing_stop_distance=Decimal(1),
        risk_reward=Decimal(2),
        position_size=10,
        position_risk=Decimal(20),
        expected_move=Decimal(4),
        confidence=Decimal("0.75"),
        reason="test signal",
    )


@pytest.mark.asyncio
async def test_ticks_and_candles_round_trip_through_sqlalchemy(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    opened_at = datetime(2026, 7, 25, 13, 30, tzinfo=UTC)
    tick_store = SqlAlchemyTickStore(sessions)
    candle_store = SqlAlchemyCandleStore(sessions)

    await tick_store.append(tick(opened_at))
    latest_tick = tick(opened_at + timedelta(seconds=1))
    await tick_store.append(latest_tick)
    assert await tick_store.latest("AAPL") == latest_tick
    assert await tick_store.list_ticks(
        "AAPL", start_at=opened_at, end_at=opened_at + timedelta(seconds=1), limit=1
    ) == (latest_tick,)

    active = Candle(
        symbol="AAPL",
        interval=CandleInterval.ONE_MINUTE,
        start_at=opened_at,
        end_at=opened_at + timedelta(minutes=1),
        open=Decimal(200),
        high=Decimal(201),
        low=Decimal(199),
        close=Decimal(200),
        volume=Decimal(100),
        is_complete=False,
    )
    await candle_store.upsert(active)
    completed = active.model_copy(update={"close": Decimal(201), "is_complete": True})
    await candle_store.upsert(completed)

    assert await candle_store.latest("AAPL", CandleInterval.ONE_MINUTE) == completed
    assert await candle_store.list_candles(
        "AAPL", CandleInterval.ONE_MINUTE, opened_at, opened_at + timedelta(minutes=1)
    ) == (completed,)


@pytest.mark.asyncio
async def test_signals_and_outcomes_are_durable(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    opened_at = datetime(2026, 7, 25, 13, 30, tzinfo=UTC)
    managed_signal = signal(opened_at)
    signal_store = SqlAlchemySignalStore(sessions)
    outcome_store = SqlAlchemyOutcomeStore(sessions)

    await signal_store.append(managed_signal)
    assert await signal_store.list_signals("AAPL") == (managed_signal,)

    outcome = ClosedSignalOutcome(
        signal=managed_signal,
        exit_price=Decimal(202),
        closed_at=opened_at + timedelta(minutes=10),
    )
    engine = AnalyticsEngine(
        AnalyticsSettings(starting_equity=Decimal(10000), reporting_timezone="America/New_York"),
        outcome_store,
    )
    await engine.record_outcome(outcome)
    assert (await engine.snapshot()).overall.total_signals == 1

@pytest.mark.asyncio
async def test_execution_audit_reserves_idempotency_and_records_portfolio(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyExecutionRepository(sessions)
    request = OrderRequest(
        client_order_id="ats-storage-test",
        symbol="AAPL",
        quantity=Decimal(10),
        side=OrderSide.BUY,
    )
    assert await repository.reserve_order(request, strategy="ema", signal_timestamp=request.created_at)
    assert not await repository.reserve_order(request, strategy="ema", signal_timestamp=request.created_at)
    await repository.record_order(
        ExecutionOrder(
            client_order_id=request.client_order_id,
            broker_order_id="broker-order-1",
            symbol="AAPL",
            quantity=Decimal(10),
            side=OrderSide.BUY,
            status=OrderLifecycleStatus.SUBMITTED,
        )
    )
    assert (await repository.list_orders())[0].broker_order_id == "broker-order-1"
    await repository.record_portfolio(
        AccountSnapshot(
            account_id="test-account",
            cash=Decimal(10_000),
            equity=Decimal(10_000),
            buying_power=Decimal(10_000),
        ),
        (),
    )


@pytest.mark.asyncio
async def test_control_configuration_and_audit_are_durable(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    settings = AppSettings(_env_file=None, symbols="AAPL")
    store = SqlAlchemyTradingControlStore(sessions)
    default = TradingControlService.from_settings(settings)

    created = await store.get_or_create(default)
    assert created.symbols == ("AAPL",)
    assert [entry.version for entry in await store.list_audit()] == [1]


def test_all_durable_models_are_registered() -> None:
    assert {
        "ticks",
        "candles",
        "signals",
        "signal_outcomes",
        "execution_orders",
        "trading_control",
        "trading_control_audit",
    } <= set(Base.metadata.tables)
    assert all((TickRecord, CandleRecord, SignalRecord, SignalOutcomeRecord))
