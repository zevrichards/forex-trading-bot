"""
Pre-trade filters — the parts of the trader's rules that gate whether to even
look for a trade, independent of the technical setup itself.

    "Trading days: Monday-Friday."
    "Trading session: London only."
    "High-impact news blackout: 15 minutes before and 30 minutes after."

All datetimes in this module are assumed to be timezone-aware and in UTC —
callers must convert before passing in. Session hours are London time, fixed
year-round with no daylight-saving shift (confirmed decision, 2026-09-14 —
not a placeholder). Because there's no DST adjustment, London time and UTC
are the same fixed offset here, so the window below is expressed directly
in UTC.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

# London session, fixed year-round (no DST shift) — confirmed 2026-09-14.
# New York session was dropped: London-only per that same decision.
LONDON_SESSION = (time(7, 0), time(16, 0))

NEWS_BLACKOUT_BEFORE = timedelta(minutes=15)
NEWS_BLACKOUT_AFTER = timedelta(minutes=30)


def is_trading_day(dt: datetime) -> bool:
    """Monday=0 ... Sunday=6; rule is Monday-Friday."""
    return dt.weekday() <= 4


def is_in_session(dt: datetime) -> bool:
    """True if dt falls within the London session window."""
    return _in_window(dt.time(), LONDON_SESSION)


def _in_window(t: time, window: tuple[time, time]) -> bool:
    start, end = window
    return start <= t <= end


def is_news_blackout(dt: datetime, high_impact_events: list[datetime]) -> bool:
    """True if dt falls within 15 minutes before or 30 minutes after ANY
    event in high_impact_events.

    high_impact_events is intentionally just a plain list of datetimes here —
    where that list comes from (an economic calendar feed/API) is not yet
    built; see README "Open questions: news calendar source."
    """
    for event_time in high_impact_events:
        window_start = event_time - NEWS_BLACKOUT_BEFORE
        window_end = event_time + NEWS_BLACKOUT_AFTER
        if window_start <= dt <= window_end:
            return True
    return False


def can_trade_now(dt: datetime, high_impact_events: list[datetime]) -> tuple[bool, str]:
    """Convenience wrapper combining all three filters into one check, with
    a human-readable reason attached — this is what the orchestrator should
    call before ever invoking the decision engine."""
    if not is_trading_day(dt):
        return False, "Not a trading day (weekend)."
    if not is_in_session(dt):
        return False, "Outside London session hours."
    if is_news_blackout(dt, high_impact_events):
        return False, "Inside high-impact news blackout window."
    return True, "OK"
