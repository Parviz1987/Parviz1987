"""Owner 27.11 22:28 (Friday night): every tile said «Əlaqə yoxdur» while the market was simply closed for the weekend.
What the owner sees is «CLOSED» then; on a weekday a silent feed is still «OFFLINE»."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.engine import Engine

NY = ZoneInfo("America/New_York")


class _E:
    def __init__(self, provider, st):
        self.provider_name, self._st = provider, st

    def status(self, symbol, now):
        return self._st


def test_a_silent_feed_is_closed_on_the_weekend_and_offline_on_a_weekday():
    sat = datetime(2026, 11, 28, 12, 0, tzinfo=NY).timestamp()
    tue = datetime(2026, 12, 1, 12, 0, tzinfo=NY).timestamp()
    assert Engine.shown_status(_E("capital", "OFFLINE"), "XAU", sat) == "CLOSED"
    assert Engine.shown_status(_E("capital", "OFFLINE"), "XAU", tue) == "OFFLINE"
    assert Engine.shown_status(_E("capital", "LIVE"), "XAU", sat) == "LIVE"
    assert Engine.shown_status(_E("demo", "DEMO"), "XAU", sat) == "DEMO"
