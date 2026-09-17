"""
evaluate_once() ties filters -> decision_engine -> stop_placement ->
risk_sizing -> order_execution together. Each piece already has its own
unit tests; these confirm the wiring itself — that a BUY decision actually
produces a correctly-computed order, and that WAIT/NO_TRADE/filtered-out
cases never reach the order executor at all.
"""

from datetime import datetime, timezone

import pytest

from src.models import Bias, Direction, MarketState, Trend
from src.order_execution import OrderExecutor, OrderResult
from src.orchestrator import build_market_state, evaluate_once
from src.relay_poller import RelaySource, RelayValues

NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)  # Wednesday, inside London session


class FakeRelaySource(RelaySource):
    def __init__(self, values: RelayValues):
        self._values = values

    def get_latest(self) -> RelayValues:
        return self._values


def make_relay_values(**overrides) -> RelayValues:
    defaults = dict(
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
        relayed_at=NOW,
    )
    defaults.update(overrides)
    return RelayValues(**defaults)


class RecordingOrderExecutor(OrderExecutor):
    def __init__(self):
        self.calls = []

    def place_market_order(self, request):
        self.calls.append(request)
        return OrderResult(status="DRY_RUN", broker_order_id=None, message="recorded")


def make_state(**overrides) -> MarketState:
    """Same clean bullish setup as test_decision_engine.py's make_state
    (box 1.1640-1.1660 -> Value 1.1650; buy-side liquidity 1.1630 below
    Value; price sitting right on it) — a BUY by default."""
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


def test_buy_decision_places_a_correctly_sized_order():
    executor = RecordingOrderExecutor()

    evaluate_once(
        make_state(), high_impact_events=[], order_executor=executor, account_balance=100_000.0
    )

    assert len(executor.calls) == 1
    order = executor.calls[0]
    assert order.direction == Direction.LONG
    assert order.symbol == "EURUSD"
    # stop = ob_projection_level(1.16100) - buffer(3 pips = 0.0003) = 1.16070
    assert order.stop_price == pytest.approx(1.16070)
    # stop distance = 23.0 pips -> lot size = 500 / (23.0 * 10.0) = 2.17
    assert order.size_lots == pytest.approx(2.17)


def test_wait_decision_does_not_place_an_order():
    executor = RecordingOrderExecutor()
    state = make_state(current_price=1.16500)  # exactly at Value -> WAIT, not BUY

    evaluate_once(state, high_impact_events=[], order_executor=executor)

    assert executor.calls == []


def test_no_trade_decision_does_not_place_an_order():
    executor = RecordingOrderExecutor()
    state = make_state(daily_bias=Bias.BEARISH)  # weekly/daily disagree -> NO_TRADE

    evaluate_once(state, high_impact_events=[], order_executor=executor)

    assert executor.calls == []


def test_outside_session_does_not_evaluate_or_place_an_order():
    executor = RecordingOrderExecutor()
    saturday = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    state = make_state(timestamp=saturday)

    evaluate_once(state, high_impact_events=[], order_executor=executor)

    assert executor.calls == []


def test_news_blackout_does_not_place_an_order():
    executor = RecordingOrderExecutor()

    evaluate_once(make_state(), high_impact_events=[NOW], order_executor=executor)

    assert executor.calls == []


def test_sell_decision_places_a_short_order():
    executor = RecordingOrderExecutor()
    state = make_state(
        current_price=1.16700,
        box_high=1.16600,
        box_low=1.16400,
        buy_liquidity=1.16300,
        sell_liquidity=1.16700,
        weekly_bias=Bias.BEARISH,
        daily_bias=Bias.BEARISH,
        trend=Trend.BEARISH,
    )

    evaluate_once(state, high_impact_events=[], order_executor=executor)

    assert len(executor.calls) == 1
    assert executor.calls[0].direction == Direction.SHORT
    # stop = ob_projection_level(1.16100) + buffer(0.0003) = 1.16130
    assert executor.calls[0].stop_price == pytest.approx(1.16130)


def test_build_market_state_computes_trend_from_boxes_by_default():
    relay = FakeRelaySource(make_relay_values(box_high=1.16700, box_low=1.16500))
    # box (1.16700/1.16500) > prev box (1.16500/1.16300) on both ends -> bullish

    state = build_market_state(relay_source=relay, current_price=1.16600)

    assert state.trend == Trend.BULLISH


def test_build_market_state_bearish_boxes():
    relay = FakeRelaySource(make_relay_values(box_high=1.16400, box_low=1.16200))
    # box (1.16400/1.16200) < prev box (1.16500/1.16300) on both ends -> bearish

    state = build_market_state(relay_source=relay, current_price=1.16300)

    assert state.trend == Trend.BEARISH


def test_build_market_state_explicit_trend_overrides_computed_one():
    relay = FakeRelaySource(make_relay_values(box_high=1.16700, box_low=1.16500))
    # Boxes alone would compute BULLISH -- explicit override should win.

    state = build_market_state(
        relay_source=relay, current_price=1.16600, trend=Trend.NEUTRAL
    )

    assert state.trend == Trend.NEUTRAL


def test_build_market_state_carries_prev_box_fields_through():
    relay = FakeRelaySource(make_relay_values())

    state = build_market_state(relay_source=relay, current_price=1.16500)

    assert state.prev_box_high == 1.16500
    assert state.prev_box_low == 1.16300
