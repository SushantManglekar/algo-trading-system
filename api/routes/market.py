"""Market-data REST endpoints."""

# ruff: noqa: B008

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_container
from market_data.tick_chart import downsample_ticks
from market_data.types import Candle, CandleInterval, HistoricalCandleRequest, MarketTick
from schemas.api import TickIngestResponse
from services.container import ApplicationContainer

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/status")
async def market_status(container: ApplicationContainer = Depends(get_container)) -> dict[str, object]:
    """Return the process-level market-data connection state."""
    return {
        "provider": container.provider.name,
        "connected": container.started and container.provider.is_connected,
        "environment": container.settings.environment,
    }


@router.post("/ticks", response_model=TickIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_tick(
    tick: MarketTick, container: ApplicationContainer = Depends(get_container)
) -> TickIngestResponse:
    """Route a tick through the same persistence, strategy, risk, and execution pipeline as workers."""
    accepted, reason, updated_count, completed_count = await container.trading_orchestrator.process_tick(tick)
    if not accepted:
        container.metrics.ticks_ingested.labels(status="dropped").inc()
        return TickIngestResponse(accepted=False, reason=reason)
    container.metrics.ticks_ingested.labels(status="accepted").inc()
    return TickIngestResponse(
        accepted=True,
        updated_candle_count=updated_count,
        completed_candle_count=completed_count,
    )


@router.get("/ticks/latest/{symbol}", response_model=MarketTick)
async def latest_tick(
    symbol: str, container: ApplicationContainer = Depends(get_container)
) -> MarketTick:
    """Return the latest accepted tick for a symbol."""
    tick = await container.tick_store.latest(symbol)
    if tick is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tick not found")
    return tick


@router.get("/ticks/{symbol}", response_model=list[MarketTick])
async def chart_ticks(
    symbol: str,
    start_at: datetime,
    end_at: datetime,
    max_points: int = 720,
    container: ApplicationContainer = Depends(get_container),
) -> list[MarketTick]:
    """Return a bounded raw-tick series suitable for a live intraday line chart."""
    if not 3 <= max_points <= 2_000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_points must be between 3 and 2000",
        )
    ticks = await container.tick_store.list_ticks(symbol, start_at=start_at, end_at=end_at)
    return list(downsample_ticks(ticks, max_points))


@router.get("/candles/latest/{symbol}", response_model=Candle)
async def latest_candle(
    symbol: str,
    interval: CandleInterval,
    container: ApplicationContainer = Depends(get_container),
) -> Candle:
    """Return the latest active or completed candle for one interval."""
    candle = await container.candle_store.latest(symbol, interval)
    if candle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="candle not found")
    return candle


@router.get("/candles/{symbol}", response_model=list[Candle])
async def historical_candles(
    symbol: str,
    interval: CandleInterval,
    start_at: datetime,
    end_at: datetime,
    adjusted: bool = True,
    container: ApplicationContainer = Depends(get_container),
) -> list[Candle]:
    """Prefer provider candles and safely aggregate stored ticks only as a fallback."""
    request = HistoricalCandleRequest(
        symbol=symbol,
        interval=interval,
        start_at=start_at,
        end_at=end_at,
        adjusted=adjusted,
    )
    provider_candles = await container.candle_history.get_provider_candles(
        request, container.provider
    )
    if provider_candles:
        return list(provider_candles)
    ticks = await container.tick_store.list_ticks(symbol, start_at=start_at, end_at=end_at)
    history = await container.candle_history.aggregate_fallback_ticks(request, ticks)
    return list(history.candles)
