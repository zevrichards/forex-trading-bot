from datetime import datetime, timezone

from src.models import Bias, Direction, MarketState, Position, Trend
from src.trade_manager import manage_position, trail_stop

NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)


def make_long_position(**overrides) -> Position:
    defaults = dict(
        direction=Direction.LONG,
        entry_price=1.16300,
        stop_price=1.16100,
        size_lots=1.67,
        entry_box_high=1.16600,
        entry_box_low=1.16400,
        partial_closed=False,
        breakeven_moved=False,
    )
    defaults.update(overrides)
    return Position(**defaults)


def make_state(**overrides) -> MarketState:
    defaults = dict(
        symbol="EURUSD",
        timestamp=NOW,
        current_price=1.16700,
        box_high=1.16600,
        box_low=1.16400,
        buy_liquidity=1.16300,
        sell_liquidity=1.16700,
        ob_projection_level=1.16100,
        stop_buffer_pips=3.0,
        weekly_bias=Bias.BULLISH,
        daily_bias=Bias.BULLISH,
        trend=Trend.BULLISH,
    )
    defaults.update(overrides)
    return MarketState(**defaults)


def test_partial_close_and_breakeven_on_opposite_liquidity_touch():
    position = make_long_position()
    state = make_state(current_price=1.16700)  # equals sell_liquidity

    actions = manage_position(position, state)

    kinds = [a.kind for a in actions]
    assert "PARTIAL_CLOSE" in kinds
    assert "MOVE_STOP" in kinds
    move_stop = next(a for a in actions if a.kind == "MOVE_STOP")
    assert move_stop.new_stop_price == position.entry_price


def test_no_partial_close_before_liquidity_touched():
    position = make_long_position()
    state = make_state(current_price=1.16500)  # short of sell_liquidity 1.16700

    actions = manage_position(position, state)

    assert all(a.kind != "PARTIAL_CLOSE" for a in actions)


def test_full_close_when_price_touches_new_box_after_partial():
    position = make_long_position(partial_closed=True)
    # Box has changed since entry (1.1660/1.1640) and price sits inside the new one.
    state = make_state(current_price=1.17050, box_high=1.17100, box_low=1.16900)

    actions = manage_position(position, state)

    assert any(a.kind == "FULL_CLOSE" for a in actions)


def test_no_full_close_if_box_unchanged_even_after_partial():
    position = make_long_position(partial_closed=True)
    state = make_state(current_price=1.16500)  # same box as entry

    actions = manage_position(position, state)

    assert all(a.kind != "FULL_CLOSE" for a in actions)


def test_hold_when_nothing_triggers():
    position = make_long_position(partial_closed=True)
    state = make_state(current_price=1.16500)  # same box, no liquidity/box event

    actions = manage_position(position, state)

    assert [a.kind for a in actions] == ["HOLD"]


def test_trail_stop_never_widens_on_long():
    # A "worse" proposed stop (lower) must be rejected in favor of the current one.
    assert trail_stop(current_stop=1.16200, proposed_stop=1.16100, direction=Direction.LONG) == 1.16200
    # A genuinely better (higher) proposed stop is accepted.
    assert trail_stop(current_stop=1.16200, proposed_stop=1.16300, direction=Direction.LONG) == 1.16300


def test_trail_stop_never_widens_on_short():
    assert trail_stop(current_stop=1.16800, proposed_stop=1.16900, direction=Direction.SHORT) == 1.16800
    assert trail_stop(current_stop=1.16800, proposed_stop=1.16700, direction=Direction.SHORT) == 1.16700
