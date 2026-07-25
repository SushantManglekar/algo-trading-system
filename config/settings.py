"""Environment-backed runtime settings for the HTTP application."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from risk.types import RiskPolicy


class TradingMode(StrEnum):
    """Alpaca account environment; paper is the only safe default."""

    PAPER = "paper"
    LIVE = "live"


class AppSettings(BaseSettings):
    """All application defaults are overridable through ``TRADING_`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="TRADING_", env_file=".env", extra="ignore")

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
    market_data_provider: str = "alpaca"
    execution_provider: str = "alpaca"
    trading_mode: TradingMode = "paper"
    order_submission_enabled: bool = False
    live_trading_confirmation: SecretStr | None = None
    alpaca_api_key: SecretStr | None = None
    alpaca_api_secret: SecretStr | None = None

    @model_validator(mode="after")
    def validate_live_trading_guard(self) -> AppSettings:
        if self.trading_mode is TradingMode.LIVE and self.order_submission_enabled:
            confirmation = (
                self.live_trading_confirmation.get_secret_value()
                if self.live_trading_confirmation is not None
                else ""
            )
            if confirmation != "ENABLE_LIVE_TRADING":
                raise ValueError("live order submission requires explicit confirmation")
        return self

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
        )
