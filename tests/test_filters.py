from datetime import datetime, timedelta, timezone

from src.filters import can_trade_now, is_in_session, is_news_blackout, is_trading_day


def test_monday_is_a_trading_day():
    monday = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    assert is_trading_day(monday)


def test_saturday_is_not_a_trading_day():
    saturday = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    assert not is_trading_day(saturday)


def test_sunday_is_not_a_trading_day():
    sunday = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    assert not is_trading_day(sunday)


def test_inside_london_session():
    dt = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
    assert is_in_session(dt)


def test_inside_new_york_session():
    dt = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)
    assert is_in_session(dt)


def test_outside_both_sessions():
    dt = datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc)  # 2am UTC, dead zone
    assert not is_in_session(dt)


def test_news_blackout_before_event():
    event = datetime(2026, 9, 9, 12, 30, tzinfo=timezone.utc)
    ten_min_before = event - timedelta(minutes=10)
    assert is_news_blackout(ten_min_before, [event])


def test_news_blackout_after_event():
    event = datetime(2026, 9, 9, 12, 30, tzinfo=timezone.utc)
    twenty_min_after = event + timedelta(minutes=20)
    assert is_news_blackout(twenty_min_after, [event])


def test_no_news_blackout_well_outside_window():
    event = datetime(2026, 9, 9, 12, 30, tzinfo=timezone.utc)
    hour_before = event - timedelta(hours=1)
    assert not is_news_blackout(hour_before, [event])


def test_can_trade_now_combines_all_three():
    good_time = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)  # Wed, London session
    can_trade, reason = can_trade_now(good_time, [])
    assert can_trade
    assert reason == "OK"


def test_can_trade_now_blocks_weekend():
    saturday = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    can_trade, reason = can_trade_now(saturday, [])
    assert not can_trade
