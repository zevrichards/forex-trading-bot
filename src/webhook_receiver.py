"""
Receives TradingView alerts from a companion Pine Script built on top of
"ATS MTF Trend V1" — the one ATS component confirmed to expose real plot
data (Bullish/Bearish Trend, Trend Start/End, Intent Level Start Dot).

NOT YET VERIFIED END TO END: a companion Pine Script exists now
(pine/ats_trend_webhook.pine) that reads ATS MTF Trend V1 via
input.source() and defines alertcondition()s on it, with its message
payload matching TradingViewAlert below exactly. But it has never been
compiled or run against the real indicator — see
docs/pine-script-verification-checklist.md for what's still unconfirmed
(mainly: whether ATS's plots actually behave the boolean on/off way the
script assumes). The payload schema below should be treated as
provisional until that checklist is done, not assumed to be exactly right.

Uses FastAPI because it's the least amount of code to get a working webhook
endpoint with request validation for free — swap freely if there's a
stack preference.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

from .models import Trend

app = FastAPI(title="EUR/USD bot — TradingView webhook receiver")

# In-memory for v1. Fine for a single-instance dev/demo deployment; swap for
# a small persistent store (SQLite is plenty) before this runs unattended
# for real, so a restart doesn't lose the last known trend.
_latest_trend: dict[str, Trend | datetime] = {}


class TradingViewAlert(BaseModel):
    """Placeholder schema — confirm against the real alert message format
    once the companion Pine script is written. TradingView alert messages
    are plain text/JSON you define yourself in the alert's "Message" field,
    so this is a proposal, not a platform requirement."""

    symbol: str
    signal: str  # expected: "bullish_trend" | "bearish_trend" | "trend_end"


@app.post("/webhook/tradingview")
def receive_alert(alert: TradingViewAlert) -> dict:
    trend = _parse_signal(alert.signal)
    _latest_trend["trend"] = trend
    _latest_trend["symbol"] = alert.symbol
    _latest_trend["received_at"] = datetime.now(timezone.utc)
    return {"status": "ok", "parsed_trend": trend}


@app.get("/trend/latest")
def get_latest_trend() -> dict:
    if not _latest_trend:
        return {"status": "no data received yet"}
    return {
        "symbol": _latest_trend["symbol"],
        "trend": _latest_trend["trend"],
        "received_at": _latest_trend["received_at"].isoformat(),
    }


def _parse_signal(signal: str) -> Trend:
    mapping = {
        "bullish_trend": Trend.BULLISH,
        "bearish_trend": Trend.BEARISH,
        "trend_end": Trend.NEUTRAL,
    }
    return mapping.get(signal, Trend.NEUTRAL)
