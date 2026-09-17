"""
Ties everything together into one evaluation loop. This is DRY-RUN ONLY —
it decides what the bot *would* do and logs it; it does not place any
orders. Wiring this to a real broker (cTrader Open API per the plan) is
the next unit of work after this decision logic has been validated against
real relayed numbers and reviewed, not before.

Run it directly (`python -m src.orchestrator`) once relay_data.json exists
(see relay_poller.py) to see a single evaluation printed to the console.
A real deployment would call `evaluate_once()` on a timer (e.g. every
minute) instead.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from . import bias, decision_engine, filters, risk_sizing, stop_placement, trade_manager
from .models import Direction, MarketState, Trend
from .news_calendar import ForexFactoryCalendarSource, NewsCalendarSource
from .order_execution import LoggingOrderExecutor, OrderExecutor, build_order_request
from .relay_poller import GoogleSheetRelaySource, JSONFileRelaySource, RelaySource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("orchestrator")

RELAY_FILE_PATH = "relay_data.json"

# The real relay: a manually-maintained Google Sheet (see docs/relay-setup.md).
# Overridable via env vars so the credentials path isn't hard-pinned to one
# machine; defaults match the current dev setup.
GOOGLE_SHEET_ID = os.environ.get(
    "RELAY_SHEET_ID", "1sSRvV4jK9GGX5fSc1vGknQOcdyiAGAvXRJGTRMk95C4"
)
GOOGLE_SHEET_CREDENTIALS_PATH = os.environ.get(
    "RELAY_SHEET_CREDENTIALS_PATH", "forex-trading-bot-508116-b2c039d424d0.json"
)

# PLACEHOLDER — the trader's own worked examples all use $100,000
# (risk_sizing.py's tests match his table exactly), but this isn't read
# from a real account anywhere. Once order execution is real, this needs
# to come from the actual broker account balance, not this constant.
ACCOUNT_BALANCE = float(os.environ.get("ACCOUNT_BALANCE", "100000"))


def build_market_state(
    relay_source: RelaySource,
    current_price: float,
    trend: Trend | None = None,
    symbol: str = "EURUSD",
) -> MarketState:
    """Combines two independent data sources into one MarketState: relayed
    values (box/prev-box/liquidity/OB projection/stop buffer/weekly+daily
    bias/structure stop level — all read visually off the trader's charts,
    see relay_poller.py) and live current price.

    `trend` defaults to None, in which case it's computed from the relayed
    box/prev-box values via bias.classify_trend_from_boxes() — see bias.py
    for why that replaced an earlier candle-fractal approach. Pass it
    explicitly to override (e.g. once ATS MTF Trend V1 via the webhook
    receiver's /trend/latest is verified, see
    docs/pine-script-verification-checklist.md, or for easy unit testing).
    """
    relay = relay_source.get_latest()
    resolved_trend = (
        trend
        if trend is not None
        else bias.classify_trend_from_boxes(
            relay.box_high, relay.box_low, relay.prev_box_high, relay.prev_box_low
        )
    )
    return MarketState(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        current_price=current_price,
        box_high=relay.box_high,
        box_low=relay.box_low,
        prev_box_high=relay.prev_box_high,
        prev_box_low=relay.prev_box_low,
        buy_liquidity=relay.buy_liquidity,
        sell_liquidity=relay.sell_liquidity,
        ob_projection_level=relay.ob_projection_level,
        stop_buffer_pips=relay.stop_buffer_pips,
        weekly_bias=relay.weekly_bias,
        daily_bias=relay.daily_bias,
        trend=resolved_trend,
        structure_stop_level=relay.structure_stop_level,
    )


def evaluate_once(
    state: MarketState,
    high_impact_events: list[datetime],
    order_executor: OrderExecutor,
    account_balance: float = ACCOUNT_BALANCE,
) -> None:
    """Runs the full pipeline: filters -> entry decision -> (if BUY/SELL)
    stop placement -> position sizing -> risk-budget guard -> order.
    order_executor defaults matter here: pass LoggingOrderExecutor (the
    default everywhere this is actually called) to keep this a dry run —
    nothing places a real order yet, see CLAUDE.md."""
    can_trade, reason = filters.can_trade_now(state.timestamp, high_impact_events)
    if not can_trade:
        logger.info("No-trade window: %s", reason)
        return

    decision = decision_engine.evaluate_entry(state)
    logger.info("Decision: %s — %s", decision.action, decision.reason)

    if decision.action not in (decision_engine.BUY, decision_engine.SELL):
        return

    direction = Direction.LONG if decision.action == decision_engine.BUY else Direction.SHORT
    stop_price = stop_placement.calculate_stop_price(
        state.ob_projection_level, direction, state.stop_buffer_pips
    )
    stop_distance = stop_placement.stop_distance_pips(state.current_price, stop_price)
    lot_size = risk_sizing.calculate_lot_size(account_balance, stop_distance)

    if risk_sizing.exceeds_risk_budget(account_balance, stop_distance, lot_size):
        logger.warning(
            "Calculated lot size %.2f on a %.1f-pip stop exceeds the risk "
            "budget — NOT placing an order.",
            lot_size,
            stop_distance,
        )
        return

    order_request = build_order_request(
        direction=direction,
        symbol=state.symbol,
        size_lots=lot_size,
        stop_price=stop_price,
    )
    result = order_executor.place_market_order(order_request)
    logger.info(
        "Order (%.2f lots, stop %.5f): %s — %s",
        lot_size,
        stop_price,
        result.status,
        result.message,
    )


def fetch_high_impact_event_times(source: NewsCalendarSource) -> list[datetime]:
    """Wraps a NewsCalendarSource for filters.can_trade_now(), which just
    wants plain datetimes. Fails open (empty list, logged) rather than
    blocking the whole evaluation on a third-party feed being unreachable —
    see news_calendar.py: this isn't an official/guaranteed-uptime API."""
    try:
        events = source.get_high_impact_events()
    except Exception:
        logger.warning(
            "Couldn't fetch the news calendar — proceeding with an empty "
            "blackout list this run.",
            exc_info=True,
        )
        return []
    return [event.time for event in events]


if __name__ == "__main__":
    # Manual smoke-test entry point. Reads from the real Google Sheet relay
    # (see docs/relay-setup.md) — weekly/daily bias and trend (via box-to-box
    # comparison) now come from there too. Set RELAY_SOURCE=json to fall
    # back to relay_data.json (relay_poller.JSONFileRelaySource) for
    # offline/local testing instead.
    if os.environ.get("RELAY_SOURCE") == "json":
        relay_source = JSONFileRelaySource(RELAY_FILE_PATH)
    else:
        relay_source = GoogleSheetRelaySource(
            sheet_id=GOOGLE_SHEET_ID,
            credentials_path=GOOGLE_SHEET_CREDENTIALS_PATH,
        )

    demo_state = build_market_state(
        relay_source=relay_source,
        current_price=1.15700,
    )
    high_impact_events = fetch_high_impact_event_times(ForexFactoryCalendarSource())
    evaluate_once(demo_state, high_impact_events, order_executor=LoggingOrderExecutor())
