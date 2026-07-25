"""Application-scoped Prometheus metrics without module-level collector state."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, generate_latest


class ApiMetrics:
    """Counters used by HTTP routes and rendered through the metrics endpoint."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.ticks_ingested = Counter(
            "trading_ticks_ingested_total",
            "Accepted or rejected ticks ingested through the REST API.",
            ["status"],
            registry=self.registry,
        )
        self.signals_generated = Counter(
            "trading_signals_generated_total",
            "Risk decisions generated through the REST API.",
            ["status"],
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)
