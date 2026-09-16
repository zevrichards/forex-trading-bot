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

from . import decision_engine, filters, trade_manager
from .models import MarketState, Trend
from .news_calendar import ForexFactoryCalendarSource, NewsCalendarSource
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


def build_market_state(
    relay_source: RelaySource,
    current_price: float,
    trend: Trend,
    symbol: str = "EURUSD",
) -> MarketState:
    """Combines two independent data sources into one MarketState: relayed
    values (box/liquidity/OB projection/stop buffer/weekly+daily bias/
    structure stop level — all read visually off the trader's charts, see
    relay_poller.py) and live current price. `trend` is the one field NOT
    in the relay — it's meant to come from ATS MTF Trend V1 via the webhook
    receiver's /trend/latest once that Pine Script is verified (see
    docs/pine-script-verification-checklist.md); passed in explicitly here
    until then, and to keep this function easy to unit test.
    """
    relay = relay_source.get_latest()
    return MarketState(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        current_price=current_price,
        box_high=relay.box_high,
        box_low=relay.box_low,
        buy_liquidity=relay.buy_liquidity,
        sell_liquidity=relay.sell_liquidity,
        ob_projection_level=relay.ob_projection_level,
        stop_buffer_pips=relay.stop_buffer_pips,
        weekly_bias=relay.weekly_bias,
        daily_bias=relay.daily_bias,
        trend=trend,
        structure_stop_level=relay.structure_stop_level,
    )


def evaluate_once(state: MarketState, high_impact_events: list[datetime]) -> None:
    can_trade, reason = filters.can_trade_now(state.timestamp, high_impact_events)
    if not can_trade:
        logger.info("No-trade window: %s", reason)
        return

    decision = decision_engine.evaluate_entry(state)
    logger.info("Decision: %s — %s", decision.action, decision.reason)
    # Sizing/order placement happen from here once decision.action is BUY/SELL
    # and a broker integration exists (see README "Not yet built").


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
    # (see docs/relay-setup.md) — weekly/daily bias now come from there too.
    # trend still hard-coded, since the webhook receiver isn't wired into
    # this loop yet. Set RELAY_SOURCE=json to fall back to relay_data.json
    # (relay_poller.JSONFileRelaySource) for offline/local testing instead.
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
        trend=Trend.BULLISH,
    )
    high_impact_events = fetch_high_impact_event_times(ForexFactoryCalendarSource())
    evaluate_once(demo_state, high_impact_events)
