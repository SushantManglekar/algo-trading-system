# Product architecture

## Goal

The platform is a local-Docker deployable trading application with a browser control surface. Operators configure watchlists, strategies, risk limits, paper/live mode, and automatic-order placement through the application. Infrastructure addresses and credentials remain deployment-only secrets.

## Component design

```mermaid
flowchart TB
    UI["Dashboard\nwatchlists, charts, signals, orders"] --> API["FastAPI control and read APIs"]
    UI <--> Events["WebSocket live-event hub"]
    API --> Control["Trading control plane\nversioned configuration and audit"]
    Control --> Runtime["Runtime coordinator\napply or pause configuration"]
    Runtime --> Pipeline["Market-data pipeline\nprovider, candles, strategies, risk"]
    Pipeline --> Execution["Execution coordinator\nidempotency and broker adapter"]
    Runtime --> Execution
    Pipeline --> Data["PostgreSQL durable records\nRedis cache"]
    Execution --> Data
    Control --> Data
    Pipeline <--> AlpacaData["Alpaca market data"]
    Execution <--> AlpacaTrade["Alpaca trading\npaper or live"]
```

| Component | Responsibility | Does not own |
| --- | --- | --- |
| Dashboard | Operator controls and at-a-glance status | Credentials or broker policy bypasses |
| Control plane | Versioned operating configuration, validation, audit | Raw market processing |
| Runtime coordinator | Applies validated configuration to workers and strategies | Persistence authority |
| Market pipeline | Ticks, candles, strategies, signals, and risk decisions | User configuration storage |
| Execution coordinator | Idempotent broker submission and portfolio reads | Strategy selection |
| PostgreSQL | Durable source of truth | Ephemeral latest-value caching |
| Redis | Reconstructible cache | Orders, signals, or audit authority |

## Safety boundaries

```mermaid
flowchart LR
    UI["UI toggle"] --> API["Validated control API"]
    API --> Audit["Versioned audit entry"]
    Audit --> Runtime["Runtime policy"]
    Runtime --> Gate1{"Monitoring enabled?"}
    Gate1 -->|No| Stop["Workers paused"]
    Gate1 -->|Yes| Gate2{"Automatic orders enabled?"}
    Gate2 -->|No| Signal["Signals and risk decisions only"]
    Gate2 -->|Yes| Gate3{"Paper or confirmed live?"}
    Gate3 --> Broker["Broker submission"]
```

The UI is not a security boundary. The backend validates configuration, records it, requires explicit confirmations for automatic and live operation, and remains the only code path able to submit orders.

## Delivery phases

1. **Control plane and dashboard foundation:** persisted watchlist/EMA/risk configuration, paper/live selector, automatic-order toggle, monitoring state, audit trail, and operator dashboard.
2. **Market intelligence:** historical charting, indicator warm-up, replay/backtesting, scanner/watchlist ranking, and news/event context.
3. **Execution productionization:** order/fill reconciliation, bracket protection, persistent kill switch, restart recovery, and execution alerts.
4. **Deployment hardening:** authentication, secret manager, TLS, backups, CI/CD, worker ownership, monitoring, and live go/no-go controls.

## Runtime configuration contract

`RuntimeTradingConfiguration` is the single persisted operator configuration. It contains:

- `mode`: `paper` or `live`.
- `place_orders_automatically`: user-visible toggle, default `false`.
- `monitoring_enabled`: start/pause market watch.
- `symbols`: normalized watchlist.
- `strategy`: selected strategy and validated parameters.
- `risk_policy`: the same immutable policy evaluated by every proposed entry.

Secrets, database URLs, provider selection, and deployment constraints remain in `.env` or a production secret manager and are never exposed in the dashboard API.
