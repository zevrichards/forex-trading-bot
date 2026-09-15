# EUR/USD Bot — v1 Skeleton

This is the first real slice of code, not a prototype of everything.
It builds and tests every part of the trader's rules that doesn't depend on
an unresolved integration question, and clearly stubs the parts that do
(the TradingView webhook, and the Google Sheet's newest columns) so
nothing about them is guessed at.

## What's built and tested (77 passing tests)

| Rule (the trader's words) | Module | Tested against |
|---|---|---|
| "$500 risk budget... Lot size = $500 / (stop pips x $10)" | `risk_sizing.py` | Every row of the trader's own lookup table, exactly |
| "BUY when price touches buy-side liquidity while below Value... SELL... above Value" | `decision_engine.py` | Clean buy/sell cases, wait cases, and a regression test that the two conditions are ANDed, not ORed |
| "Weekly + Daily bias must agree... Trend must agree with the bias" | `decision_engine.py` | Conflicting/neutral bias, trend disagreement. `weekly_bias`/`daily_bias` are now relayed (see below), not computed |
| "Bullish trend = HH + HL. Bearish trend = LL + LH." | `bias.py` (unused, see below) | Hand-built, hand-verified candle sequences for bullish, bearish, insufficient structure, and a genuinely conflicting (ambiguous) case |
| "Stop is outside the ATS Order Block Projection, with a small manually determined buffer" | `stop_placement.py` | LONG/SHORT stop calc, zero-buffer edge case — buffer is now a relayed value, not a placeholder constant |
| "Close 50% when opposite-side liquidity is touched, move remaining stop to breakeven" | `trade_manager.py` | Triggers correctly, doesn't fire early |
| "Exit the remaining 50% when price enters/touches a new ATS-identified Box" | `trade_manager.py` | Triggers only after partial close + a genuinely new box |
| "Never widen the stop" | `trade_manager.py` (`trail_stop`) | Enforced as a hard invariant on both long and short, independent of what proposes the new stop |
| "Trading days: Monday-Friday. Session: London only, fixed, no DST." | `filters.py` | Weekday/weekend, in/out of session |
| "News blackout: 15 min before, 30 min after" | `filters.py` | Before/after/outside the window |

Run the tests yourself: `pip install -r requirements.txt && pytest -v`

**`bias.py` note (2026-09-15):** its `classify_trend()` is real, tested
code, but it's never actually called from `orchestrator.py` or
`decision_engine.py` — checked directly, not assumed. It was an attempt to
compute trend from raw candles, which turned out not to match how the
trader thinks (see Open Questions history below); `trend` now comes from
either the ATS MTF Trend V1 webhook (once verified) or manual override, and
`weekly_bias`/`daily_bias` are relayed values. `bias.py` is safe to leave
alone or remove later — it isn't blocking anything.

One real bug got caught during this build, worth knowing about: the
trader's own worked example (30 pips -> 1.67 lots) technically risks $501,
one dollar over the $500 budget, purely from rounding to the nearest
tradeable 0.01 lot. The risk-budget guard was originally too strict and
would have rejected their own example. Fixed by tolerating half a
lot-step's worth of unavoidable rounding — see the comment in
`risk_sizing.py` for the full reasoning. This is exactly the kind of thing
testing against their real numbers was for.

## What's live

**`relay_poller.py`** — reading the ATS Box/liquidity/OB-projection numbers,
plus (as of 2026-09-15) stop buffer, weekly/daily bias, and the trailing-
stop's structure level — see Open Questions history below for why those
four joined the relay instead of being computed. Confirmed via live testing
that the ATS numbers can't be read programmatically (see the WhatsApp
conversation history / plan docs for the screen-share findings).
`GoogleSheetRelaySource` reads the last row of a manually-maintained Google
Sheet (no Form, values are typed in directly) via `gspread`, and has been
run successfully end-to-end against the real Sheet with the original 7
columns — see `docs/relay-setup.md` for the setup and the current full
10-column schema. **The live Sheet needs the 3 newest columns (Weekly Bias,
Daily Bias, Structure Stop Level) added before the orchestrator will run
again** — it currently only has through Stop Buffer. `JSONFileRelaySource`
still works for offline/local testing (`RELAY_SOURCE=json`). The Sheet
currently holds placeholder/test values, not real ATS numbers yet.

## What's stubbed, and why

**`webhook_receiver.py`** — receiving ATS MTF Trend V1's bias signal, which
*is* confirmed live-readable. The endpoint works (tested). A companion Pine
Script now exists too (`pine/ats_trend_webhook.pine`), reading ATS MTF
Trend V1 via `input.source()` and firing `alertcondition()`s whose message
payload matches this endpoint's schema exactly. What's not done: the
script has never been compiled or run against the real indicator — see
`docs/pine-script-verification-checklist.md` for what's unconfirmed
(mainly whether ATS's plots behave the simple on/off way the script
assumes). Treat the payload schema
(`{"symbol": ..., "signal": "bullish_trend"}`) as provisional until that
checklist is done.

**Not started at all:**
- Order execution (cTrader Open API integration) — nothing places a real
  order yet; `orchestrator.py` only logs what it *would* do.
- Candle history fetch for `bias.py` to run on live data (it's tested with
  hand-built fixtures, not wired to a real data source yet).
- The actual trailing-stop rule ("after a new higher-low forms, move stop
  below it") — `trade_manager._trail_stop()` is a deliberate no-op stub;
  see Open Questions below.
- An economic calendar feed for the news blackout filter — `filters.py`
  takes a plain list of event times; nothing populates that list yet.

## Open questions to resolve before this goes further

~~**Session hours.**~~ Resolved 2026-09-14: London session only (New York
dropped), fixed year-round with no DST shift. `filters.py` updated.

~~**Stop buffer size.**~~ Resolved 2026-09-15: rather than a fixed pip
constant, the trader's own source material (`docs/trader-strategy-source.md`
item 15: "not simply an arbitrary 10 or 20 pips... sits slightly below it
depending on structure") describes the buffer as structural/contextual, not
universal. So it's now a 6th manually-relayed value (`stop_buffer_pips`) —
see `relay_poller.py`, `models.MarketState`, `docs/relay-setup.md`. The
`DEFAULT_BUFFER_PIPS` constant is gone; `stop_placement.calculate_stop_price`
now requires `buffer_pips` explicitly.

~~**Swing-point detection for the real trailing-stop rule.**~~ Resolved
differently than expected, 2026-09-15: not by getting a better definition,
but by making the question moot. Asked the trader directly on 2026-09-14
using "swing point" terminology and it didn't land ("Swing point? You mean
liquidity?"); followed up 2026-09-15 asking him to circle highs/lows on
real charts and he sent screenshots marking "order block" candles and leg
distances instead — still not a definition the bot could use. Rather than
keep pushing (he's not going to produce a formula for something he
processes visually), `weekly_bias`/`daily_bias`/`structure_stop_level` are
now manually-relayed values, the same fix as the stop buffer above —
see `docs/relay-setup.md`. `bias.py`'s fractal `classify_trend()` was
never actually wired into the live pipeline (checked directly — not
called from `orchestrator.py` or `decision_engine.py`), so it's now
dead code rather than a blocker; safe to leave as-is or remove later,
doesn't need further work.

1. **News calendar source.** Needs an actual feed (a scraped calendar, a
   paid API) to populate the blackout list — nothing chosen yet.

## Project layout

```
src/
  models.py          shared data types (MarketState, Position, etc.)
  risk_sizing.py      position sizing from the 0.5% risk rule
  decision_engine.py  entry logic (BUY/SELL/WAIT/NO_TRADE)
  stop_placement.py   initial stop from the OB projection level
  trade_manager.py    partial close / breakeven / full close / never-widen
  bias.py             weekly/daily bias + trend from swing structure
  filters.py          trading day / session / news blackout gate
  relay_poller.py     where the manually-relayed ATS numbers come from
  webhook_receiver.py FastAPI endpoint for ATS MTF Trend V1 alerts
  orchestrator.py     ties it together, dry-run only (no order placement)
pine/
  ats_trend_webhook.pine  companion Pine Script for webhook_receiver.py — drafted, unverified (see docs/pine-script-verification-checklist.md)
tests/                59 tests, one file per src module (except stop_placement)
```
