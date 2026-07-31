"""Environment-backed runtime settings for the HTTP application."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from re import fullmatch
from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from market_data.types import CandleInterval
from risk.types import RiskPolicy


class TradingMode(StrEnum):
    """Alpaca account environment; paper is the only safe default."""

    PAPER = "paper"
    LIVE = "live"


class StorageBackend(StrEnum):
    """Persistence implementation selected for the running process."""

    MEMORY = "memory"
    POSTGRES = "postgres"


class ProviderName(StrEnum):
    """Supported provider implementations; unknown values must fail at configuration load."""

    ALPACA = "alpaca"
    MOCK = "mock"


class AlpacaDataFeed(StrEnum):
    """Alpaca equities feed entitlement selected without changing provider code."""

    IEX = "iex"
    SIP = "sip"


def _split_symbols(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        symbols = tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
    elif isinstance(value, (list, tuple)):
        symbols = tuple(str(symbol).strip().upper() for symbol in value if str(symbol).strip())
    else:
        raise TypeError("symbols must be a comma-separated string or sequence")
    if len(set(symbols)) != len(symbols):
        raise ValueError("symbols must be unique")
    if any(fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol) is None for symbol in symbols):
        raise ValueError("symbols must be valid uppercase equity symbols")
    return symbols


ConfiguredSymbols = Annotated[tuple[str, ...], BeforeValidator(_split_symbols)]


class AppSettings(BaseSettings):
    """All application defaults are overridable through ``TRADING_`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TRADING_", env_file=".env", extra="ignore", enable_decoding=False
    )

    app_name: str = "Intraday Signal Platform"
    environment: str = "development"
    tick_buffer_per_symbol: int = Field(default=10_000, gt=0)
    candle_buffer_per_series: int = Field(default=10_000, gt=0)
    analytics_starting_equity: Decimal = Field(default=Decimal(100_000), gt=Decimal(0))
    analytics_reporting_timezone: str = "America/New_York"
    risk_per_trade_fraction: Decimal = Field(default=Decimal("0.01"), gt=Decimal(0), le=Decimal(1))
    max_daily_loss_fraction: Decimal = Field(default=Decimal("0.02"), gt=Decimal(0), le=Decimal(1))
    max_consecutive_losses: int = Field(default=3, ge=1)
    stop_atr_multiple: Decimal = Field(default=Decimal("1.5"), gt=Decimal(0))
    target_atr_multiple: Decimal = Field(default=Decimal(3), gt=Decimal(0))
    trailing_stop_atr_multiple: Decimal = Field(default=Decimal(1), gt=Decimal(0))
    minimum_risk_reward: Decimal = Field(default=Decimal(2), ge=Decimal(1))
    market_data_provider: ProviderName = ProviderName.MOCK
    execution_provider: ProviderName = ProviderName.MOCK
    alpaca_data_feed: AlpacaDataFeed = AlpacaDataFeed.IEX
    trading_mode: TradingMode = "paper"
    order_submission_enabled: bool = False
    automation_enabled: bool = False
    automation_confirmation: SecretStr | None = None
    symbols: ConfiguredSymbols = ()
    worker_count: int = Field(default=2, ge=1, le=32)
    worker_queue_size: int = Field(default=2_000, ge=100, le=100_000)
    atr_period: int = Field(default=14, ge=2, le=200)
    strategy_interval: CandleInterval = CandleInterval.ONE_MINUTE
    ema_fast_period: int = Field(default=12, ge=2, le=500)
    ema_slow_period: int = Field(default=26, ge=3, le=1_000)
    ema_base_confidence: Decimal = Field(default=Decimal("0.60"), ge=Decimal(0), le=Decimal(1))
    ema_confidence_sensitivity: Decimal = Field(default=Decimal(10), gt=Decimal(0))
    ema_max_confidence: Decimal = Field(default=Decimal("0.95"), ge=Decimal(0), le=Decimal(1))
    max_gross_exposure_fraction: Decimal = Field(default=Decimal("0.80"), gt=Decimal(0), le=Decimal(1))
    minimum_cash_reserve_fraction: Decimal = Field(default=Decimal("0.10"), ge=Decimal(0), lt=Decimal(1))
    max_open_positions: int = Field(default=10, ge=1, le=500)
    live_trading_confirmation: SecretStr | None = None
    alpaca_api_key: SecretStr | None = None
    alpaca_api_secret: SecretStr | None = None
    alpaca_live_api_key: SecretStr | None = None
    alpaca_live_api_secret: SecretStr | None = None
    storage_backend: StorageBackend = StorageBackend.MEMORY
    database_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    @model_validator(mode="after")
    def validate_live_trading_guard(self) -> AppSettings:
        if (
            self.market_data_provider is ProviderName.ALPACA
            or self.execution_provider is ProviderName.ALPACA
        ) and not self._has_alpaca_credentials():
            raise ValueError("Alpaca providers require non-empty API key and secret")
        if self.trading_mode is TradingMode.LIVE and self.order_submission_enabled:
            confirmation = (
                self.live_trading_confirmation.get_secret_value()
                if self.live_trading_confirmation is not None
                else ""
            )
            if confirmation != "ENABLE_LIVE_TRADING":
                raise ValueError("live order submission requires explicit confirmation")
        if (
            self.trading_mode is TradingMode.LIVE
            and self.execution_provider is ProviderName.ALPACA
            and not self._has_alpaca_live_credentials()
        ):
            raise ValueError("live Alpaca execution requires a separate non-empty live API key and secret")
        if self.automation_enabled and not self.order_submission_enabled:
            raise ValueError("automation requires order_submission_enabled=true")
        if self.automation_enabled:
            confirmation = (
                self.automation_confirmation.get_secret_value()
                if self.automation_confirmation is not None
                else ""
            )
            expected = "ENABLE_LIVE_AUTOMATION" if self.trading_mode is TradingMode.LIVE else "ENABLE_PAPER_AUTOMATION"
            if confirmation != expected:
                raise ValueError("automation requires explicit mode-specific confirmation")
        if self.ema_fast_period >= self.ema_slow_period:
            raise ValueError("ema_fast_period must be lower than ema_slow_period")
        if not self.symbols and self.automation_enabled:
            raise ValueError("automation requires at least one configured symbol")
        return self

    def _has_alpaca_credentials(self) -> bool:
        return bool(
            self.alpaca_api_key is not None
            and self.alpaca_api_key.get_secret_value().strip()
            and self.alpaca_api_secret is not None
            and self.alpaca_api_secret.get_secret_value().strip()
        )

    def has_alpaca_live_credentials(self) -> bool:
        """Return whether an independent Alpaca live credential pair is configured."""
        return self._has_alpaca_live_credentials()

    def _has_alpaca_live_credentials(self) -> bool:
        return bool(
            self.alpaca_live_api_key is not None
            and self.alpaca_live_api_key.get_secret_value().strip()
            and self.alpaca_live_api_secret is not None
            and self.alpaca_live_api_secret.get_secret_value().strip()
        )

    def risk_policy(self) -> RiskPolicy:
        """Construct the immutable policy consumed by the risk domain service."""
        return RiskPolicy(
            risk_per_trade_fraction=self.risk_per_trade_fraction,
            max_daily_loss_fraction=self.max_daily_loss_fraction,
            max_consecutive_losses=self.max_consecutive_losses,
            stop_atr_multiple=self.stop_atr_multiple,
            target_atr_multiple=self.target_atr_multiple,
            trailing_stop_atr_multiple=self.trailing_stop_atr_multiple,
            minimum_risk_reward=self.minimum_risk_reward,
            max_gross_exposure_fraction=self.max_gross_exposure_fraction,
            minimum_cash_reserve_fraction=self.minimum_cash_reserve_fraction,
            max_open_positions=self.max_open_positions,
        )
