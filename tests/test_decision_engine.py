from datetime import datetime, timezone

from src.decision_engine import BUY, NO_TRADE, SELL, WAIT, evaluate_entry
from src.models import Bias, MarketState, Trend

NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)


def make_state(**overrides) -> MarketState:
    """A clean bullish setup by default (box 1.1640-1.1660, so Value = 1.1650;
    buy-side liquidity at 1.1630 below Value; price sitting right on it),
    with every field overridable per test."""
    defaults = dict(
        symbol="EURUSD",
        timestamp=NOW,
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


def test_buy_when_all_conditions_align():
    decision = evaluate_entry(make_state())
    assert decision.action == BUY


def test_sell_when_all_bearish_conditions_align():
    state = make_state(
        current_price=1.16700,
        weekly_bias=Bias.BEARISH,
        daily_bias=Bias.BEARISH,
        trend=Trend.BEARISH,
    )
    decision = evaluate_entry(state)
    assert decision.action == SELL


def test_no_trade_when_weekly_and_daily_bias_disagree():
    state = make_state(weekly_bias=Bias.BULLISH, daily_bias=Bias.BEARISH)
    decision = evaluate_entry(state)
    assert decision.action == NO_TRADE


def test_no_trade_when_bias_is_neutral():
    state = make_state(weekly_bias=Bias.NEUTRAL, daily_bias=Bias.NEUTRAL)
    assert evaluate_entry(state).action == NO_TRADE


def test_no_trade_when_trend_disagrees_with_bullish_bias():
    state = make_state(trend=Trend.BEARISH)
    assert evaluate_entry(state).action == NO_TRADE


def test_wait_when_bullish_but_price_not_below_value_yet():
    # Value = (1.1660 + 1.1640) / 2 = 1.1650; price above it.
    state = make_state(current_price=1.16550)
    assert evaluate_entry(state).action == WAIT


def test_wait_when_below_value_but_liquidity_not_touched_yet():
    state = make_state(current_price=1.16450)  # below value, above buy_liquidity
    assert evaluate_entry(state).action == WAIT


def test_buy_not_triggered_merely_by_touching_liquidity_above_value():
    # Regression guard: liquidity touch alone isn't enough without the
    # below-value condition — this checks the two conditions are ANDed,
    # not ORed.
    state = make_state(
        current_price=1.16300,  # at buy_liquidity
        box_high=1.16200,       # but Value is now BELOW current price
        box_low=1.16000,
    )
    assert evaluate_entry(state).action == WAIT
