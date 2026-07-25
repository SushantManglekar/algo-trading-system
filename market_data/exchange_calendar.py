"""XNYS exchange-session boundaries used for market-data aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import exchange_calendars as xcals
import pandas as pd

from market_data.types import CandleInterval

_INTRADAY_DURATIONS: dict[CandleInterval, pd.Timedelta] = {
    CandleInterval.ONE_MINUTE: pd.Timedelta(minutes=1),
    CandleInterval.TWO_MINUTES: pd.Timedelta(minutes=2),
    CandleInterval.THREE_MINUTES: pd.Timedelta(minutes=3),
    CandleInterval.FIVE_MINUTES: pd.Timedelta(minutes=5),
    CandleInterval.TEN_MINUTES: pd.Timedelta(minutes=10),
    CandleInterval.FIFTEEN_MINUTES: pd.Timedelta(minutes=15),
    CandleInterval.THIRTY_MINUTES: pd.Timedelta(minutes=30),
    CandleInterval.FORTY_FIVE_MINUTES: pd.Timedelta(minutes=45),
    CandleInterval.ONE_HOUR: pd.Timedelta(hours=1),
    CandleInterval.TWO_HOURS: pd.Timedelta(hours=2),
    CandleInterval.FOUR_HOURS: pd.Timedelta(hours=4),
}


@dataclass(frozen=True, slots=True)
class CandleBucket:
    """An exchange-calendar-aware interval with explicit UTC boundaries."""

    start_at: datetime
    end_at: datetime


class XnysExchangeCalendar:
    """Resolves US equities candle boundaries from the maintained XNYS schedule."""

    def __init__(self) -> None:
        self._calendar = xcals.get_calendar("XNYS")

    def bucket_for(self, timestamp: datetime, interval: CandleInterval) -> CandleBucket | None:
        """Return the regular-session bucket containing a timestamp, if any."""
        tick_time = self._as_utc_timestamp(timestamp)
        if not self._calendar.is_open_on_minute(tick_time, ignore_breaks=True):
            return None

        session = self._calendar.minute_to_session(tick_time, direction="none")
        session_open = self._calendar.session_open(session)
        session_close = self._calendar.session_close(session)
        if interval in _INTRADAY_DURATIONS:
            duration = _INTRADAY_DURATIONS[interval]
            elapsed = tick_time - session_open
            start = session_open + (elapsed // duration) * duration
            end = min(start + duration, session_close)
        elif interval is CandleInterval.DAILY:
            start, end = session_open, session_close
        elif interval is CandleInterval.WEEKLY:
            start, end = self._week_boundaries(session)
        elif interval is CandleInterval.MONTHLY:
            start, end = self._month_boundaries(session)
        else:  # pragma: no cover - protects future enum expansion.
            raise ValueError(f"unsupported candle interval: {interval}")
        return CandleBucket(start_at=start.to_pydatetime(), end_at=end.to_pydatetime())

    def _week_boundaries(self, session: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
        week_start = session - pd.Timedelta(days=session.weekday())
        week_end = week_start + pd.Timedelta(days=6)
        first_session = self._calendar.date_to_session(week_start, direction="next")
        last_session = self._calendar.date_to_session(week_end, direction="previous")
        return self._calendar.session_open(first_session), self._calendar.session_close(last_session)

    def _month_boundaries(self, session: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
        month_start = session.replace(day=1)
        month_end = month_start + pd.offsets.MonthEnd(0)
        first_session = self._calendar.date_to_session(month_start, direction="next")
        last_session = self._calendar.date_to_session(month_end, direction="previous")
        return self._calendar.session_open(first_session), self._calendar.session_close(last_session)

    @staticmethod
    def _as_utc_timestamp(timestamp: datetime) -> pd.Timestamp:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return pd.Timestamp(timestamp.astimezone(UTC))
