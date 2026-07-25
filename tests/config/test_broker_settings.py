from decimal import Decimal

import pytest
from pydantic import ValidationError

from config.settings import AppSettings, TradingMode


def test_paper_trading_is_the_safe_default() -> None:
    settings = AppSettings(
        analytics_starting_equity=Decimal(10_000),
        tick_buffer_per_symbol=10,
        candle_buffer_per_series=10,
    )

    assert settings.trading_mode is TradingMode.PAPER
    assert settings.order_submission_enabled is False


def test_live_order_submission_requires_explicit_confirmation() -> None:
    with pytest.raises(ValidationError, match="explicit confirmation"):
        AppSettings(
            analytics_starting_equity=Decimal(10_000),
            tick_buffer_per_symbol=10,
            candle_buffer_per_series=10,
            trading_mode=TradingMode.LIVE,
            order_submission_enabled=True,
        )


def test_automation_requires_explicit_mode_confirmation_and_symbols() -> None:
    with pytest.raises(ValidationError, match="mode-specific confirmation"):
        AppSettings(order_submission_enabled=True, automation_enabled=True, symbols="AAPL")

    settings = AppSettings(
        order_submission_enabled=True,
        automation_enabled=True,
        automation_confirmation="ENABLE_PAPER_AUTOMATION",
        symbols="aapl,msft",
    )
    assert settings.symbols == ("AAPL", "MSFT")
