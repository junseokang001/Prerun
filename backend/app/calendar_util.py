"""Trading-day calendars for projecting future dates. Historical days come from the price series."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")

# Built-in exchange holidays. Temporary closures may be missing; the UI says so.
KRX_HOLIDAYS = {
    date(2026, 1, 1),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 3, 2),
    date(2026, 5, 1),
    date(2026, 5, 5),
    date(2026, 5, 25),
    date(2026, 8, 17),
    date(2026, 9, 24),
    date(2026, 9, 25),
    date(2026, 9, 28),
    date(2026, 10, 5),
    date(2026, 10, 9),
    date(2026, 12, 25),
    date(2026, 12, 31),
    date(2027, 1, 1),
}

NYSE_HOLIDAYS = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
}


def now_kst() -> datetime:
    return datetime.now(KST)


def tz_for(market: str):
    return ET if market == "US" else KST


def holidays_for(market: str) -> set[date]:
    return NYSE_HOLIDAYS if market == "US" else KRX_HOLIDAYS


def is_trading_day(d: date, market: str) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in holidays_for(market)


def session_state(market: str, moment: datetime | None = None) -> str:
    """Return 'open' or 'closed'."""
    moment = moment or datetime.now(tz_for(market))
    local = moment.astimezone(tz_for(market))
    if not is_trading_day(local.date(), market):
        return "closed"
    t = local.time()
    if market == "US":
        return "open" if time(9, 30) <= t < time(16, 0) else "closed"
    return "open" if time(9, 0) <= t < time(15, 30) else "closed"


def add_trading_days(start: date, n: int, market: str) -> date:
    """The trading day n sessions after start. n=1 is the next session."""
    if n <= 0:
        return start
    d = start
    left = n
    guard = 0
    while left > 0 and guard < 400:
        d += timedelta(days=1)
        guard += 1
        if is_trading_day(d, market):
            left -= 1
    return d


def offset_date(bar_dates: list[date], signal_index: int, offset: int, market: str, signal_date: date) -> date:
    """Trading day `offset` sessions after the signal day."""
    if offset <= 0:
        return signal_date
    target = signal_index + offset
    if 0 <= signal_index < len(bar_dates) and target < len(bar_dates):
        return bar_dates[target]
    if 0 <= signal_index < len(bar_dates):
        extra = target - (len(bar_dates) - 1)
        return add_trading_days(bar_dates[-1], extra, market)
    return add_trading_days(signal_date, offset, market)


def short_md(d: date) -> str:
    return f"{d.month}/{d.day}"


def korean_date(d: date) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일"
