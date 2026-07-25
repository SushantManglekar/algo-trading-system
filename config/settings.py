"""Environment-backed runtime settings for the HTTP application."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from risk.types import RiskPolicy


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
