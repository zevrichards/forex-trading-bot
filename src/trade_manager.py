"""
Managing an open position — everything that happens between entry and exit.

Rules, verbatim:
    "When opposite-side liquidity is touched, close 50% of the position and
    move the remaining position's stop to breakeven."
    "Exit the remaining 50% when price enters/touches a new ATS-identified Box."
    "Do NOT move the stop simply because you're in profit... Never widen the
    stop simply to avoid getting stopped." "Long stop -> progressively higher.
    Short stop -> progressively lower."

manage_position() is a pure function: given a Position and the current
MarketState, it returns the list of actions that should happen right now.
It does not place orders itself — see order_execution.py (not yet built,
see README) for turning these into actual broker calls.
"""

from __future__ import annotations

from .models import Direction, ManagementAction, MarketState, Position

PARTIAL_CLOSE_FRACTION = 0.5  # "close 50% of the position"


def manage_position(position: Position, state: MarketState) -> list[ManagementAction]:
    actions: list[ManagementAction] = []

    if not position.partial_closed:
        if _opposite_liquidity_touched(position, state):
            actions.append(
                ManagementAction(
                    "PARTIAL_CLOSE",
                    "Opposite-side liquidity touched — closing 50% per rule.",
                    close_fraction=PARTIAL_CLOSE_FRACTION,
                )
            )
            actions.append(
                ManagementAction(
                    "MOVE_STOP",
                    "Moving remaining position's stop to breakeven per rule.",
                    new_stop_price=position.entry_price,
                )
            )
        return actions  # nothing else happens before the partial close

    # From here on, position.partial_closed is True.
    if _new_box_touched(position, state):
        actions.append(
            ManagementAction(
                "FULL_CLOSE",
                "Price has entered/touched a new ATS-identified Box — "
                "exiting the remaining 50% per rule.",
            )
        )
        return actions

    trailed_stop = _trail_stop(position, state)
    if trailed_stop is not None and trailed_stop != position.stop_price:
        actions.append(
            ManagementAction(
                "MOVE_STOP",
                "New structure level relayed — tightening stop (never widening).",
                new_stop_price=trailed_stop,
            )
        )

    if not actions:
        actions.append(ManagementAction("HOLD", "No management action triggered."))

    return actions


def _opposite_liquidity_touched(position: Position, state: MarketState) -> bool:
    if position.direction == Direction.LONG:
        # Entered on buy-side liquidity; the opposing side is sell-side liquidity.
        return state.current_price >= state.sell_liquidity
    else:
        return state.current_price <= state.buy_liquidity


def _new_box_touched(position: Position, state: MarketState) -> bool:
    box_has_changed = (
        state.box_high != position.entry_box_high or state.box_low != position.entry_box_low
    )
    price_in_new_box = state.box_low <= state.current_price <= state.box_high
    return box_has_changed and price_in_new_box


def trail_stop(current_stop: float, proposed_stop: float, direction: Direction) -> float:
    """Enforces 'never widen the stop' as a hard invariant, independent of
    whatever produced the proposed new stop (a new higher-low/lower-high,
    a manual override, anything). This function is the one place that rule
    is enforced, so every other caller can propose freely without risk.
    """
    if direction == Direction.LONG:
        return max(current_stop, proposed_stop)  # only ever moves up
    else:
        return min(current_stop, proposed_stop)  # only ever moves down


def _trail_stop(position: Position, state: MarketState) -> float | None:
    """The trader's rule: "after price establishes a new higher-low ->
    higher-high, move the stop below the newly established higher-low"
    (mirrored for shorts). Detecting that algorithmically turned out to
    need a "swing point" concept the trader doesn't think in — asked him
    directly on 2026-09-15 and it didn't land (see
    docs/trader-strategy-source.md, conversation log same date). Same fix
    as stop_buffer_pips: he relays the current structure-stop level
    directly (state.structure_stop_level) instead of the bot detecting it.

    Returns None if nothing's been relayed (no new structure to trail to
    yet). Every non-None result still goes through trail_stop() so a stale
    or backwards relayed value can never widen the stop.
    """
    if state.structure_stop_level is None:
        return None
    return trail_stop(position.stop_price, state.structure_stop_level, position.direction)
