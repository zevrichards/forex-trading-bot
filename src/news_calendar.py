"""
Populates filters.py's news blackout list. Previously nothing did this —
orchestrator.py just had HIGH_IMPACT_NEWS_EVENTS: list[datetime] = [].

    "Before high-impact news (FOMC, Fed Chair speech, ECB decision/speech,
    CPI, PCE, NFP, major GDP, major geopolitical announcement): if a
    technical setup is forming immediately before the event, don't blindly
    enter." (docs/trader-strategy-source.md item 15/24)

This module defines one interface (NewsCalendarSource) so the rest of the
system doesn't care where the event list physically comes from — same
pattern as relay_poller.RelaySource.
"""

from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

# Only USD/EUR news moves EUR/USD directly — filtering here keeps the
# blackout list to what's actually relevant, per the trader's own rule.
RELEVANT_CURRENCIES = {"USD", "EUR"}


@dataclass(frozen=True)
class HighImpactEvent:
    name: str
    currency: str
    time: datetime  # timezone-aware, UTC
    impact: str  # "Low" | "Medium" | "High", as the feed reports it


class NewsCalendarSource(ABC):
    @abstractmethod
    def get_high_impact_events(self) -> list[HighImpactEvent]:
        """Returns every High-impact USD/EUR event currently in the
        source's window (whatever window that is — see the concrete class).
        Should not raise on a single malformed entry; skip it instead."""


class ForexFactoryCalendarSource(NewsCalendarSource):
    """Reads the "FairEconomy" mirror of the ForexFactory calendar
    (nfs.faireconomy.media) — an unofficial, free, no-signup JSON feed
    widely used by retail EA calendar-filter indicators. Confirmed live
    and reachable on 2026-09-15 (real HTTP 200, real JSON matching the
    shape parsed below) — not assumed to work, actually tested.

    This is NOT an official API: no uptime or schema-stability guarantee,
    could change or go away without notice. That's why it's behind
    NewsCalendarSource — swap in something official (a paid calendar API)
    later without touching filters.py or orchestrator.py.

    Also rate-limited — confirmed 2026-09-15: an initial fetch returned a
    clean 200 with valid JSON, but two more fetches within the same minute
    (verification + a real orchestrator run) got 403 then 429. Fine for
    orchestrator.py's current one-shot manual runs; once this runs on a
    timer for real, cache the result and refetch at most once every 15-30
    minutes rather than calling get_high_impact_events() on every tick —
    high-impact events don't move that fast anyway.

    The feed only covers "this week" — refresh by re-fetching, there's no
    historical/future query parameter on this endpoint.
    """

    DEFAULT_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(self, url: str = DEFAULT_URL, timeout_seconds: float = 10.0):
        self.url = url
        self.timeout_seconds = timeout_seconds

    def get_high_impact_events(self) -> list[HighImpactEvent]:
        return self._parse(self._fetch_raw())

    def _fetch_raw(self) -> list[dict]:
        with urllib.request.urlopen(self.url, timeout=self.timeout_seconds) as response:
            return json.loads(response.read())

    @staticmethod
    def _parse(raw: list[dict]) -> list[HighImpactEvent]:
        events: list[HighImpactEvent] = []
        for item in raw:
            if item.get("impact") != "High":
                continue
            currency = item.get("country")
            if currency not in RELEVANT_CURRENCIES:
                continue
            try:
                event_time = datetime.fromisoformat(item["date"]).astimezone(timezone.utc)
            except (KeyError, ValueError, TypeError):
                continue  # malformed row — skip it rather than crash the whole feed
            events.append(
                HighImpactEvent(
                    name=item.get("title", "Unknown event"),
                    currency=currency,
                    time=event_time,
                    impact=item["impact"],
                )
            )
        return events


class StaticNewsCalendarSource(NewsCalendarSource):
    """Wraps a plain list — for tests, and as a manual override/fallback
    when the live feed is unreachable or you want to hand-specify events."""

    def __init__(self, events: list[HighImpactEvent] | None = None):
        self._events = list(events) if events else []

    def get_high_impact_events(self) -> list[HighImpactEvent]:
        return list(self._events)
