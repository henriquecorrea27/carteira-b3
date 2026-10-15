"""Watchlist: tickers alerted on Discord only by the price against the SMA200 (zones, changes, schedule, API)."""

from datetime import date, datetime, timedelta
from decimal import Decimal as D

import pytest

from app.api.portfolio import get_market_provider
from app.core.config import get_settings
from app.core.profiles import primary_profile
from app.main import app
from app.market_data.base import DailyBar
from app.models import PriceHistory, ReportDispatch, WatchlistItem
from app.notifications import service
from app.notifications.watchlist import ABOVE, BELOW, CHEAP, EXPENSIVE, limits, zone

THU = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 19, 5)


class FakeNotifier:
    name = "fake"
    max_length = 2000

    def __init__(self):
        self.sent: list[list[str]] = []

    def send(self, messages):
        self.sent.append(messages)


def weekdays(end: date, n: int) -> list[date]:
    days, day = [], end
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return list(reversed(days))


def series(end: date, last: str, n: int = 200) -> dict[date, D]:
    """n sessions at R$ 10 and the last one at `last`: SMA200 = (199 × 10 + last) / 200."""
    days = weekdays(end, n)
    return {d: D("10") for d in days[:-1]} | {days[-1]: D(last)}


def seed_prices(s, ticker: str, closes: dict[date, D]) -> None:
    for day, value in closes.items():
        s.add(PriceHistory(ticker=ticker, date=day, close=value, close_adjusted=value, source="t"))


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        ("-0.25", CHEAP),
        ("-0.10", CHEAP),
        ("-0.0999", BELOW),
        ("0", ABOVE),
        ("0.0999", ABOVE),
        ("0.10", EXPENSIVE),
    ],
)
def test_zones_use_the_chart_analysis_limits(distance, expected):
    assert zone(D(distance), limits()) == expected


# --- alert content and schedule ---------------------------------------------------------------


def _seed_watchlist(session_factory):
    with session_factory() as s:
        s.add_all(
            [
                WatchlistItem(ticker="AAAA3", note="esperar o balanço"),
                WatchlistItem(ticker="BBBB4"),
                WatchlistItem(ticker="CCCC3"),
            ]
        )
        seed_prices(s, "AAAA3", series(THU, "8"))  # SMA 9,99 → −19,9%
        seed_prices(s, "BBBB4", series(THU, "12"))  # SMA 10,01 → +19,9%
        seed_prices(s, "CCCC3", series(THU, "10", n=50))  # not enough history
        s.commit()


def test_scheduled_alert_reports_zones_then_zone_changes(client, session_factory):
    _seed_watchlist(session_factory)
    notifier = FakeNotifier()
    with session_factory() as s:
        run = service.run_scheduled(s, notifier, NOW, kind=service.WATCHLIST)
        assert run.status == "SENT"
        assert service.run_scheduled(s, notifier, NOW, kind=service.WATCHLIST).status == "ALREADY_SENT"
        first = s.query(ReportDispatch).one()
        assert (first.kind, first.decisions) == ("WATCHLIST", {"AAAA3": CHEAP, "BBBB4": EXPENSIVE})
        text = first.content
        assert text.startswith("## 📈 Lista de observação · MM200 · qui, 08/10/2026")
        assert "Primeiro aviso" in text
        assert (
            "### 🟢 10% ou mais abaixo da MM200 (1)\n**AAAA3** R$ 8,00 · MM200 R$ 9,99 · **−19,9%**" in text
        )
        assert "-# esperar o balanço" in text
        assert (
            "### 🔴 10% ou mais acima da MM200 (1)\n**BBBB4** R$ 12,00 · MM200 R$ 10,01 · **+19,9%**" in text
        )
        assert "### ⚪ Sem MM200\n**CCCC3** R$ 10,00 · só 50 pregões de histórico" in text

        # Friday: AAAA3 recovers to 4% below the SMA → zone change on top
        seed_prices(s, "AAAA3", {date(2026, 10, 9): D("9.6")})
        s.commit()
        run = service.run_scheduled(s, notifier, datetime(2026, 10, 9, 19, 5), kind=service.WATCHLIST)
        assert run.status == "SENT"
        second = s.query(ReportDispatch).order_by(ReportDispatch.id.desc()).first()
    assert (
        "### 🔔 Mudanças de faixa\n**AAAA3**: 🟢 10% ou mais abaixo da MM200 → **🟡 abaixo da MM200** · "
        "R$ 9,60 (−3,9%)"
    ) in second.content
    assert "BBBB4**:" not in second.content  # unchanged zones are not alerts
    assert len(notifier.sent) == 2


def test_watchlist_and_daily_report_are_logged_apart(client, session_factory):
    _seed_watchlist(session_factory)
    with session_factory() as s:
        assert service.run_scheduled(s, FakeNotifier(), NOW, kind=service.WATCHLIST).status == "SENT"
        assert service.run_scheduled(s, FakeNotifier(), NOW).status == "SENT"  # the daily report still goes
        assert service.last_sent(s).kind == "DAILY"
        assert [d.kind for d in service.recent_dispatches(s, kind=service.WATCHLIST)] == ["WATCHLIST"]


def test_empty_watchlist_sends_nothing(session_factory):
    notifier = FakeNotifier()
    with session_factory() as s:
        assert service.run_scheduled(s, notifier, NOW, kind=service.WATCHLIST).status == "EMPTY"
    assert notifier.sent == []


def test_channel_separate_or_shared(monkeypatch):
    settings, p = get_settings(), primary_profile()
    monkeypatch.setattr(settings, "discord_webhook_url", "https://discord.test/main")
    monkeypatch.setattr(settings, "discord_watchlist_webhook_url", "")
    assert service.watchlist_channel(p) == "SHARED"
    assert service.get_watchlist_notifier(p)._url == "https://discord.test/main"
    monkeypatch.setattr(settings, "discord_watchlist_webhook_url", "https://discord.test/mm200")
    assert service.watchlist_channel(p) == "SEPARATE"
    assert service.get_watchlist_notifier(p)._url == "https://discord.test/mm200"
    monkeypatch.setattr(settings, "discord_webhook_url", "")
    monkeypatch.setattr(settings, "discord_watchlist_webhook_url", "")
    assert (service.watchlist_channel(p), service.get_watchlist_notifier(p)) == (None, None)


# --- API --------------------------------------------------------------------------------------


class FakeMarket:
    name = "fake"

    def __init__(self, closes: dict[str, dict[date, D]]):
        self.closes = closes

    def daily_bars(self, tickers, start, end):
        return {
            t: [DailyBar(d, v, v, D(1000)) for d, v in sorted(self.closes[t].items()) if start <= d <= end]
            for t in tickers
            if t in self.closes
        }


def test_api_add_list_edit_remove(client):
    today = service.local_now().date()
    app.dependency_overrides[get_market_provider] = lambda: FakeMarket(
        {"AAAA3": series(today, "8"), "BBBB4": series(today, "10.5")}
    )
    added = client.post("/api/watchlist", json={"ticker": "aaaa3f", "note": "  "})
    assert added.status_code == 201
    body = added.json()
    assert (body["ticker"], body["zone"], body["note"], body["sma"]) == ("AAAA3", CHEAP, None, "9.9900")
    assert round(float(body["distance"]), 4) == -0.1992
    assert client.post("/api/watchlist", json={"ticker": "AAAA3"}).status_code == 409
    assert client.post("/api/watchlist", json={"ticker": "ZZZZ3"}).status_code == 404  # no quotes
    assert client.post("/api/watchlist", json={"ticker": "ABCDEF"}).status_code == 422
    assert client.post("/api/watchlist", json={"ticker": "BBBB4"}).status_code == 201

    listed = client.get("/api/watchlist").json()
    assert [(i["ticker"], i["zone"]) for i in listed["items"]] == [("AAAA3", CHEAP), ("BBBB4", ABOVE)]
    assert (listed["sma_days"], listed["cheap"], listed["expensive"]) == (200, "-0.1", "0.1")

    patched = client.patch("/api/watchlist/BBBB4", json={"note": "comprar abaixo da média"}).json()
    assert patched["note"] == "comprar abaixo da média"
    preview = client.get("/api/watchlist/preview").json()
    assert "-# comprar abaixo da média" in preview["content"]

    assert client.delete("/api/watchlist/AAAA3").status_code == 204
    assert client.delete("/api/watchlist/AAAA3").status_code == 404
    assert [i["ticker"] for i in client.get("/api/watchlist").json()["items"]] == ["BBBB4"]


def test_api_manual_send(client, session_factory):
    _seed_watchlist(session_factory)
    notifier = FakeNotifier()
    app.dependency_overrides[service.get_watchlist_notifier] = lambda: notifier
    sent = client.post("/api/watchlist/send")
    assert sent.status_code == 200
    assert sent.json()["trigger"] == "MANUAL"
    assert len(notifier.sent) == 1
    # A manual send never counts as the scheduled alert of the day
    with session_factory() as s:
        assert service.last_sent(s, kind=service.WATCHLIST) is None
    assert [d["trigger"] for d in client.get("/api/watchlist/dispatches").json()] == ["MANUAL"]
