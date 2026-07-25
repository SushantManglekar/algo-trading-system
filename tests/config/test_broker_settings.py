from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import AppSettings, ProviderName, TradingMode


def test_paper_trading_is_the_safe_default() -> None:
    settings = AppSettings(
        _env_file=None,
        analytics_starting_equity=Decimal(10_000),
        tick_buffer_per_symbol=10,
        candle_buffer_per_series=10,
    )

    assert settings.trading_mode is TradingMode.PAPER
    assert settings.order_submission_enabled is False


def test_live_order_submission_requires_explicit_confirmation() -> None:
    with pytest.raises(ValidationError, match="explicit confirmation"):
        AppSettings(
            _env_file=None,
            analytics_starting_equity=Decimal(10_000),
            tick_buffer_per_symbol=10,
            candle_buffer_per_series=10,
            trading_mode=TradingMode.LIVE,
            order_submission_enabled=True,
        )


def test_automation_requires_explicit_mode_confirmation_and_symbols() -> None:
    with pytest.raises(ValidationError, match="mode-specific confirmation"):
        AppSettings(
            _env_file=None, order_submission_enabled=True, automation_enabled=True, symbols="AAPL"
        )

    settings = AppSettings(
        _env_file=None,
        order_submission_enabled=True,
        automation_enabled=True,
        automation_confirmation="ENABLE_PAPER_AUTOMATION",
        symbols="aapl,msft",
    )
    assert settings.symbols == ("AAPL", "MSFT")


def test_alpaca_selection_requires_credentials_and_symbols_are_validated() -> None:
    with pytest.raises(ValidationError, match="Alpaca providers require"):
        AppSettings(
            _env_file=None,
            market_data_provider=ProviderName.ALPACA,
            alpaca_api_key=None,
            alpaca_api_secret=None,
        )

    with pytest.raises(ValidationError, match="symbols must be unique"):
        AppSettings(_env_file=None, symbols="AAPL,AAPL")

    with pytest.raises(ValidationError, match="valid uppercase equity symbols"):
        AppSettings(_env_file=None, symbols="not a symbol")


def test_environment_template_covers_every_operational_setting() -> None:
    template = Path(__file__).parents[2] / ".env.example"
    configured_names = {
        line.split("=", maxsplit=1)[0]
        for line in template.read_text(encoding="utf-8").splitlines()
        if line.startswith("TRADING_") and "=" in line
    }
    excluded_internal_defaults = {"app_name"}
    expected_names = {
        f"TRADING_{name.upper()}"
        for name in AppSettings.model_fields
        if name not in excluded_internal_defaults
    }
    assert expected_names <= configured_names


def test_csv_symbols_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_SYMBOLS", "aapl,msft")
    settings = AppSettings(_env_file=None)
    assert settings.symbols == ("AAPL", "MSFT")
