# Intraday Signal Platform

Phase 1 foundation for a production-grade US equities data and trading-signal platform.
It generates and records signals only; it does not submit or manage orders.

## Architecture

The codebase follows clean-architecture boundaries:

- `api`: REST and WebSocket delivery.
- `market_data` and `providers`: provider contracts and market-data ingestion.
- `strategies`, `risk`, `signals`, and `analytics`: domain capabilities.
- `storage`, `repositories`, and `models`: persistence boundary.
- `services`, `workers`, and `events`: orchestration and asynchronous workflows.
- `config` and `core`: configuration and cross-cutting infrastructure.

Each module will be introduced incrementally, with no order-execution capability in Phase 1.
