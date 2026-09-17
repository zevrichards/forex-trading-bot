"""
test_trade_manager.py checks manage_position() one call at a time. This file
instead runs a full position lifecycle — a sequence of MarketState snapshots
fed through manage_position() in order, applying each returned action back
onto a mutable Position copy — and asserts invariants hold across the whole
sequence, not just within a single call. This is where a bug in the
*ordering* of rules (e.g. trailing firing before the partial close, a second
partial close, a widened stop slipping through) would actually show up;
single-call tests can't catch that by construction.
"""

from datetime import datetime, timedelta, timezone

from src.models import Bias, Direction, MarketState, Position, Trend
from src.trade_manager import manage_position

START = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)


def make_position(**overrides) -> Position:
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


def make_state(step: int, **overrides) -> MarketState:
    defaults = dict(
        symbol="EURUSD",
        timestamp=START + timedelta(minutes=30 * step),
        current_price=1.16300,
        box_high=1.16600,
        box_low=1.16400,
        prev_box_high=1.16500,
        prev_box_low=1.16300,
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


def simulate(position: Position, states: list[MarketState]) -> list[list[str]]:
    """Feeds states through manage_position() in order, mutating position
    per the returned actions, asserting invariants at every step. Returns
    the per-step list of action kinds for the caller's own assertions.
    Stops early if FULL_CLOSE fires (nothing meaningful happens after)."""
    history: list[list[str]] = []
    partial_seen = False

    for state in states:
        actions = manage_position(position, state)
        kinds = [a.kind for a in actions]
        history.append(kinds)

        if "HOLD" in kinds:
            assert kinds == ["HOLD"], f"HOLD combined with other actions: {kinds}"

        for action in actions:
            if action.kind == "PARTIAL_CLOSE":
                assert not partial_seen, "PARTIAL_CLOSE fired more than once in the lifecycle"
                partial_seen = True
                position.partial_closed = True
            elif action.kind == "MOVE_STOP":
                new_stop = action.new_stop_price
                if position.direction == Direction.LONG:
                    assert new_stop >= position.stop_price, (
                        f"Stop widened on LONG: {position.stop_price} -> {new_stop}"
                    )
                else:
                    assert new_stop <= position.stop_price, (
                        f"Stop widened on SHORT: {position.stop_price} -> {new_stop}"
                    )
                position.stop_price = new_stop
            elif action.kind == "FULL_CLOSE":
                assert partial_seen, "FULL_CLOSE fired before any PARTIAL_CLOSE"

        if any(a.kind == "FULL_CLOSE" for a in actions):
            break

    return history


def test_long_full_favorable_lifecycle():
    position = make_position()
    states = [
        make_state(0, current_price=1.16400),  # below sell_liquidity -> HOLD
        make_state(1, current_price=1.16700),  # touches sell_liquidity -> partial + breakeven
        make_state(2, current_price=1.16750, structure_stop_level=1.16450),  # trails up
        make_state(3, current_price=1.16800, structure_stop_level=1.16500),  # trails up again
        # Bad/stale relayed value (lower than current stop) must be ignored, not applied.
        make_state(4, current_price=1.16900, structure_stop_level=1.16400),
        # New box forms and price sits inside it -> full close.
        make_state(5, current_price=1.16900, box_high=1.17000, box_low=1.16800),
    ]

    history = simulate(position, states)

    assert history[0] == ["HOLD"]
    assert set(history[1]) == {"PARTIAL_CLOSE", "MOVE_STOP"}
    assert history[2] == ["MOVE_STOP"]
    assert history[3] == ["MOVE_STOP"]
    assert history[4] == ["HOLD"]  # bad data correctly rejected, no spurious move
    assert history[5] == ["FULL_CLOSE"]
    assert position.stop_price == 1.16500  # step 4's bad value never got applied


def test_short_full_favorable_lifecycle():
    position = make_position(
        direction=Direction.SHORT,
        entry_price=1.16800,
        stop_price=1.17000,
        entry_box_high=1.16800,
        entry_box_low=1.16600,
    )
    base = dict(
        buy_liquidity=1.16300,
        sell_liquidity=1.16900,
        box_high=1.16800,
        box_low=1.16600,
        weekly_bias=Bias.BEARISH,
        daily_bias=Bias.BEARISH,
        trend=Trend.BEARISH,
    )
    states = [
        make_state(0, current_price=1.16600, **base),  # above buy_liquidity -> HOLD
        make_state(1, current_price=1.16300, **base),  # touches buy_liquidity -> partial + breakeven
        make_state(2, current_price=1.16250, structure_stop_level=1.16600, **base),
        make_state(3, current_price=1.16200, structure_stop_level=1.16700, **base),  # would widen
        make_state(
            4,
            current_price=1.16300,
            box_high=1.16400,
            box_low=1.16200,
            **{k: v for k, v in base.items() if k not in ("box_high", "box_low")},
        ),
    ]

    history = simulate(position, states)

    assert history[0] == ["HOLD"]
    assert set(history[1]) == {"PARTIAL_CLOSE", "MOVE_STOP"}
    assert history[2] == ["MOVE_STOP"]
    assert history[3] == ["HOLD"]  # bad data (would widen) correctly rejected
    assert history[4] == ["FULL_CLOSE"]
    assert position.stop_price == 1.16600  # step 3's bad value never got applied


def test_flat_price_path_never_triggers_anything():
    position = make_position()
    states = [make_state(i, current_price=1.16300) for i in range(5)]

    history = simulate(position, states)

    assert all(kinds == ["HOLD"] for kinds in history)


def test_structure_stop_level_ignored_before_partial_close():
    """A relayed trailing level shouldn't do anything until after the
    partial-close/breakeven step has actually happened — trailing is only
    meant to apply to the remaining 50%."""
    position = make_position()
    state = make_state(
        0,
        current_price=1.16400,  # hasn't touched sell_liquidity yet
        structure_stop_level=1.16450,  # would be a valid trail target once eligible
    )

    actions = manage_position(position, state)

    assert [a.kind for a in actions] == ["HOLD"]
