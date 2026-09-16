"""
Places real orders. Currently the only implementation that actually sends
anything anywhere is LoggingOrderExecutor (dry-run) — it matches
orchestrator.py's current "logs what it would do" behavior and is the
default until a real broker integration exists and is reviewed (see
CLAUDE.md: "Nothing places a real order yet.").

CTraderOrderExecutor's request-building logic (_build_new_order_proto) is
real and unit-tested against the actual `ctrader-open-api` PyPI package's
protobuf message shapes — confirmed 2026-09-15 by installing the package
and introspecting its real ProtoOANewOrderReq/ProtoOAOrderType/
ProtoOATradeSide descriptors directly, plus the official docs at
help.ctrader.com/open-api, not guessed from memory. What's genuinely NOT
done: sending anything over the wire. That needs a live cTrader demo
account (an app registered at openapi.ctrader.com for client_id/
client_secret, an OAuth access token tied to a specific
ctidTraderAccountId, and EURUSD's symbolId for that specific broker —
symbolId is broker-specific, not a universal constant, resolved via
ProtoOASymbolsListReq). None of that exists yet and can't be built/tested
honestly without it — place_market_order() raises NotImplementedError,
same reasoning relay_poller.GoogleSheetRelaySource was a stub before the
real Sheet existed. Do not guess at what "should" work for the connection
lifecycle (Twisted-based: connect -> app auth -> account auth -> send).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .models import Direction

UNITS_PER_LOT = 100_000
VOLUME_SCALE = 100  # cTrader Open API: volume field is units * 100 ("cents") — confirmed 2026-09-15


@dataclass(frozen=True)
class OrderRequest:
    """Everything needed to place one market order — the output of
    decision_engine.py + risk_sizing.py + stop_placement.py, ready to submit."""

    symbol: str
    direction: Direction
    size_lots: float
    stop_price: float
    take_profit_price: float | None = None
    comment: str = ""


@dataclass(frozen=True)
class OrderResult:
    status: str  # "PLACED" | "DRY_RUN" | "FAILED"
    broker_order_id: str | None
    message: str


class OrderExecutor(ABC):
    @abstractmethod
    def place_market_order(self, request: OrderRequest) -> OrderResult:
        """Places (or simulates placing) one market order."""


class LoggingOrderExecutor(OrderExecutor):
    """Doesn't place anything — logs what it would do. orchestrator.py's
    default until a real broker integration exists and has been reviewed."""

    def __init__(self):
        self._logger = logging.getLogger("order_execution")

    def place_market_order(self, request: OrderRequest) -> OrderResult:
        tp_part = f", TP {request.take_profit_price:.5f}" if request.take_profit_price else ""
        self._logger.info(
            "DRY RUN — would place %s %s %.2f lots, stop %.5f%s",
            request.direction.value.upper(),
            request.symbol,
            request.size_lots,
            request.stop_price,
            tp_part,
        )
        return OrderResult(status="DRY_RUN", broker_order_id=None, message="Logged only, not sent.")


def volume_in_cents(size_lots: float) -> int:
    """Converts a lot size to cTrader's volume unit: units * 100 ("cents",
    per the Open API docs — confirmed 2026-09-15, not assumed). 1.0 lot =
    100,000 units = 10,000,000 in this field."""
    return round(size_lots * UNITS_PER_LOT * VOLUME_SCALE)


def build_order_request(
    direction: Direction,
    symbol: str,
    size_lots: float,
    stop_price: float,
    take_profit_price: float | None = None,
    comment: str = "",
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        direction=direction,
        size_lots=size_lots,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        comment=comment,
    )


class CTraderOrderExecutor(OrderExecutor):
    """See module docstring — _build_new_order_proto is real and tested;
    place_market_order is not implemented and needs a live demo account
    before it honestly can be."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str,
        ctid_trader_account_id: int,
        symbol_id_map: dict[str, int],
        demo: bool = True,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.ctid_trader_account_id = ctid_trader_account_id
        self.symbol_id_map = symbol_id_map
        self.demo = demo

    def _build_new_order_proto(self, request: OrderRequest):
        """Maps our OrderRequest to a real ProtoOANewOrderReq. Field names,
        the MARKET/BUY/SELL enum values, and the volume/stopLoss/takeProfit
        units are all confirmed against the installed ctrader-open-api
        package and official docs (2026-09-15) — not assumed. stopLoss/
        takeProfit are absolute prices (not relative distances — those are
        separate relativeStopLoss/relativeTakeProfit fields we don't use)."""
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOANewOrderReq
        from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
            ProtoOAOrderType,
            ProtoOATradeSide,
        )

        if request.symbol not in self.symbol_id_map:
            raise ValueError(
                f"No symbolId configured for {request.symbol!r} — resolve it via "
                "ProtoOASymbolsListReq once (broker-specific, not a universal "
                "constant) and add it to symbol_id_map."
            )

        proto = ProtoOANewOrderReq()
        proto.ctidTraderAccountId = self.ctid_trader_account_id
        proto.symbolId = self.symbol_id_map[request.symbol]
        proto.orderType = ProtoOAOrderType.MARKET
        proto.tradeSide = (
            ProtoOATradeSide.BUY if request.direction == Direction.LONG else ProtoOATradeSide.SELL
        )
        proto.volume = volume_in_cents(request.size_lots)
        proto.stopLoss = request.stop_price
        if request.take_profit_price is not None:
            proto.takeProfit = request.take_profit_price
        if request.comment:
            proto.comment = request.comment
        return proto

    def place_market_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError(
            "CTraderOrderExecutor's connection lifecycle isn't built yet — "
            "needs a live cTrader demo account to build and test honestly "
            "(see class/module docstring). _build_new_order_proto() is real "
            "and tested; only the actual network send is missing."
        )
