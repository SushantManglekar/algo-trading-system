"""Bounded, symbol-sharded background workers for provider market-data streams."""

from __future__ import annotations

import asyncio
import logging

from market_data.provider import MarketDataProvider
from market_data.types import MarketTick
from services.trading_orchestrator import TradingOrchestrator

logger = logging.getLogger(__name__)


class TradingPipelineWorker:
    """Preserves ordering within a symbol while processing independent symbols in parallel."""

    def __init__(
        self,
        provider: MarketDataProvider,
        orchestrator: TradingOrchestrator,
        symbols: tuple[str, ...],
        worker_count: int,
        queue_size: int,
    ) -> None:
        self._provider = provider
        self._orchestrator = orchestrator
        self._symbols = symbols
        self._queues = [asyncio.Queue[MarketTick](maxsize=queue_size) for _ in range(worker_count)]
        self._producer: asyncio.Task[None] | None = None
        self._consumers: list[asyncio.Task[None]] = []

    @property
    def is_running(self) -> bool:
        return self._producer is not None and not self._producer.done()

    async def start(self) -> None:
        if self.is_running or not self._symbols:
            return
        await self._orchestrator.initialize()
        await self._provider.subscribe(self._symbols)
        self._consumers = [
            asyncio.create_task(self._consume(queue), name=f"trading-worker-{index}")
            for index, queue in enumerate(self._queues)
        ]
        self._producer = asyncio.create_task(self._produce(), name="market-data-producer")

    async def stop(self) -> None:
        tasks = [task for task in [self._producer, *self._consumers] if task is not None]
        self._producer = None
        self._consumers = []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._symbols and self._provider.is_connected:
            await self._provider.unsubscribe(self._symbols)

    async def _produce(self) -> None:
        async for tick in self._provider.stream_ticks():
            await self._queues[hash(tick.symbol) % len(self._queues)].put(tick)

    async def _consume(self, queue: asyncio.Queue[MarketTick]) -> None:
        while True:
            tick = await queue.get()
            try:
                await self._orchestrator.process_tick(tick)
            except Exception:
                logger.exception("trading_pipeline_tick_failed", extra={"symbol": tick.symbol})
