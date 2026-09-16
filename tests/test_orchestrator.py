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
from src.orchestrator import evaluate_once

NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)  # Wednesday, inside London session


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
