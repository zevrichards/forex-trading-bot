"""
LoggingOrderExecutor and the pure helpers (volume_in_cents, build_order_request)
are fully tested. CTraderOrderExecutor._build_new_order_proto is tested
against the REAL installed ctrader-open-api package — not a mock — since
its whole value is confirming our request matches the actual protobuf
shape (field names, enum values, units) rather than a guess. Its
place_market_order() is not implemented; that's tested too, as an
explicit NotImplementedError, not left unverified.
"""

import pytest

from src.models import Direction
from src.order_execution import (
    CTraderOrderExecutor,
    LoggingOrderExecutor,
    OrderResult,
    build_order_request,
    volume_in_cents,
)


def test_volume_in_cents_one_lot():
    assert volume_in_cents(1.0) == 10_000_000


def test_volume_in_cents_fractional_lot():
    # Matches risk_sizing.py's own worked example: 30 pips -> 1.67 lots.
    assert volume_in_cents(1.67) == 16_700_000


def test_volume_in_cents_smallest_lot_step():
    assert volume_in_cents(0.01) == 100_000


def test_build_order_request_defaults():
    request = build_order_request(
        direction=Direction.LONG,
        symbol="EURUSD",
        size_lots=1.67,
        stop_price=1.16100,
    )
    assert request.take_profit_price is None
    assert request.comment == ""


def test_logging_order_executor_returns_dry_run(caplog):
    executor = LoggingOrderExecutor()
    request = build_order_request(
        direction=Direction.LONG,
        symbol="EURUSD",
        size_lots=1.67,
        stop_price=1.16100,
        take_profit_price=1.16700,
    )

    result = executor.place_market_order(request)

    assert result == OrderResult(status="DRY_RUN", broker_order_id=None, message="Logged only, not sent.")


def test_logging_order_executor_never_raises_for_missing_take_profit():
    executor = LoggingOrderExecutor()
    request = build_order_request(
        direction=Direction.SHORT, symbol="EURUSD", size_lots=0.5, stop_price=1.17000
    )
    result = executor.place_market_order(request)
    assert result.status == "DRY_RUN"


# --- CTraderOrderExecutor: request-building tested against the real package ---

SYMBOL_MAP = {"EURUSD": 1}


def make_executor(**overrides):
    defaults = dict(
        client_id="test-client-id",
        client_secret="test-client-secret",
        access_token="test-access-token",
        ctid_trader_account_id=12345,
        symbol_id_map=SYMBOL_MAP,
    )
    defaults.update(overrides)
    return CTraderOrderExecutor(**defaults)


def test_build_new_order_proto_long_matches_real_message_shape():
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAOrderType,
        ProtoOATradeSide,
    )

    executor = make_executor()
    request = build_order_request(
        direction=Direction.LONG,
        symbol="EURUSD",
        size_lots=1.67,
        stop_price=1.16100,
        take_profit_price=1.16700,
    )

    proto = executor._build_new_order_proto(request)

    assert proto.ctidTraderAccountId == 12345
    assert proto.symbolId == 1
    assert proto.orderType == ProtoOAOrderType.MARKET
    assert proto.tradeSide == ProtoOATradeSide.BUY
    assert proto.volume == 16_700_000
    assert proto.stopLoss == pytest.approx(1.16100)
    assert proto.takeProfit == pytest.approx(1.16700)


def test_build_new_order_proto_short_uses_sell_side():
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATradeSide

    executor = make_executor()
    request = build_order_request(
        direction=Direction.SHORT, symbol="EURUSD", size_lots=0.5, stop_price=1.17000
    )

    proto = executor._build_new_order_proto(request)

    assert proto.tradeSide == ProtoOATradeSide.SELL


def test_build_new_order_proto_omits_take_profit_when_not_given():
    executor = make_executor()
    request = build_order_request(
        direction=Direction.LONG, symbol="EURUSD", size_lots=1.0, stop_price=1.16100
    )

    proto = executor._build_new_order_proto(request)

    assert not proto.HasField("takeProfit")


def test_build_new_order_proto_unknown_symbol_raises():
    executor = make_executor()
    request = build_order_request(
        direction=Direction.LONG, symbol="GBPUSD", size_lots=1.0, stop_price=1.25000
    )

    with pytest.raises(ValueError, match="No symbolId configured"):
        executor._build_new_order_proto(request)


def test_place_market_order_not_implemented():
    executor = make_executor()
    request = build_order_request(
        direction=Direction.LONG, symbol="EURUSD", size_lots=1.0, stop_price=1.16100
    )

    with pytest.raises(NotImplementedError, match="connection lifecycle"):
        executor.place_market_order(request)
