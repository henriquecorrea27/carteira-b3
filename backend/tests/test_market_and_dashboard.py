import json
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

import httpx
import pandas as pd
import pytest

from app.api.portfolio import get_market_provider, get_rates_provider
from app.main import app
from app.market_data.base import DailyBar, MarketDataError
from app.market_data.bcb import BCBRatesProvider, parse_sgs
from app.market_data.yfinance_provider import unadjust

TODAY = date.today()


def days_ago(n):
    return TODAY - timedelta(days=n)


class FakeMarket:
    name = "fake"

    def __init__(self, closes: dict[str, dict[date, str]], fail: bool = False):
        self.closes, self.fail = closes, fail

    def daily_bars(self, tickers, start, end):
        if self.fail:
            raise MarketDataError("offline")
        return {
            t: [
                DailyBar(d, D(v), D(v), D(1000))
                for d, v in sorted(self.closes[t].items())
                if start <= d <= end
            ]
            for t in tickers
            if t in self.closes
        }

    def index_closes(self, symbol, start, end):
        if self.fail:
            raise MarketDataError("offline")
        return [(days_ago(n), D(100 + (40 - n))) for n in range(40, -1, -1) if start <= days_ago(n) <= end]


class FakeRates:
    name = "fake"

    def cdi_daily(self, start, end):
        return [(days_ago(n), D("0.05")) for n in range(40, -1, -1) if start <= days_ago(n) <= end]


@pytest.fixture
def market(client):
    def install(closes, fail=False):
        app.dependency_overrides[get_market_provider] = lambda: FakeMarket(closes, fail)
        app.dependency_overrides[get_rates_provider] = lambda: FakeRates()

    return install


def _seed(client):
    items = [
        {"date": days_ago(30).isoformat(), "ticker": "WEGE3", "type": "BUY", "quantity": "10", "price": "40"},
        {
            "date": days_ago(30).isoformat(),
            "ticker": "HGLG11",
            "type": "BUY",
            "quantity": "2",
            "price": "150",
        },
        {
            "date": days_ago(20).isoformat(),
            "ticker": "WEGE3",
            "type": "DIVIDEND",
            "quantity": "10",
            "price": "1",
            "payment_date": days_ago(10).isoformat(),
        },
        {
            "date": days_ago(5).isoformat(),
            "ticker": "HGLG11",
            "type": "INCOME",
            "quantity": "2",
            "price": "1.10",
            "payment_date": (TODAY + timedelta(days=10)).isoformat(),
        },
    ]
    assert client.post("/api/transactions/batch", json={"items": items}).status_code == 201


PRICES = {
    "WEGE3": {days_ago(31): "39", days_ago(30): "40", days_ago(1): "48", TODAY: "50"},
    "HGLG11": {days_ago(30): "150", TODAY: "150"},
}


def test_refresh_then_positions_have_market_values(client, market):
    _seed(client)
    market(PRICES)
    res = client.post("/api/market-data/refresh").json()
    assert res["errors"] == []
    assert res["prices_inserted"] == 6

    positions = {p["ticker"]: p for p in client.get("/api/portfolio/positions").json()}
    wege = positions["WEGE3"]
    assert (wege["current_price"], wege["market_value"], wege["open_result"]) == ("50", "500.00", "100.00")
    assert wege["open_result_pct"] == "0.25"
    assert wege["day_change_pct"] == "0.04166667"  # 50 / 48 − 1
    assert wege["provents_net_12m"] == "10.00"
    assert wege["yield_on_cost_pct"] == "0.025"  # 10 / 400
    assert wege["weight_pct"] == "0.625"  # 500 / 800
    assert positions["HGLG11"]["asset_class"] == "FII"

    # Refresh is incremental and idempotent
    assert client.post("/api/market-data/refresh").json()["prices_inserted"] == 0


def test_refresh_replaces_an_intraday_price_with_the_close(client, market):
    _seed(client)
    market(PRICES)
    client.post("/api/market-data/refresh")  # during the session: WEGE3 at 50
    market({**PRICES, "WEGE3": {**PRICES["WEGE3"], days_ago(1): "47", TODAY: "52"}})
    assert client.post("/api/market-data/refresh").json()["prices_inserted"] == 0

    wege = {p["ticker"]: p for p in client.get("/api/portfolio/positions").json()}["WEGE3"]
    assert (wege["current_price"], wege["day_change_pct"]) == ("52", "0.10638298")  # 52 / 47 − 1


def test_summary_history_and_allocation(client, market):
    _seed(client)
    market(PRICES)
    client.post("/api/market-data/refresh")
    summary = client.get("/api/portfolio/summary").json()
    assert summary["invested"] == "700.00"
    assert summary["market_value"] == "800.00"
    assert summary["open_result"] == "100.00"
    assert summary["provents_net_total"] == "10.00"
    assert summary["provents_receivable"] == "2.20"
    assert summary["total_result"] == "110.00"
    # TWR: dividend day 710/700, then 780/700 (WEGE3 40 → 48) and 800/780 → 710/700 × 800/700 − 1
    assert D(summary["return_total"]).quantize(D("0.0001")) == D("0.1592")
    assert summary["prices_as_of"] == TODAY.isoformat()
    assert summary["cdi_12m"] is not None

    hist = client.get("/api/portfolio/history", params={"range": "1m"}).json()
    assert hist[-1]["market_value"] == "800.00"
    assert hist[-1]["invested"] == "700.00"

    alloc = client.get("/api/portfolio/allocation").json()
    assert [(s["key"], s["pct"]) for s in alloc["by_class"]] == [("STOCK", "0.625"), ("FII", "0.375")]
    assert alloc["by_sector"][0]["label"] == "Sem setor"


def test_provents_summary_and_list(client, market):
    _seed(client)
    summary = client.get("/api/provents/summary").json()
    assert summary["received_12m"] == "10.00"
    assert summary["receivable"] == "2.20"
    assert [u["ticker"] for u in summary["upcoming"]] == ["HGLG11"]
    assert summary["by_asset_12m"][0] == {"ticker": "WEGE3", "net_amount": "10.00", "pct": "1"}
    months = {m["month"]: m for m in summary["monthly"]}
    assert months[f"{days_ago(10):%Y-%m}"]["received"] in ("10.00",)

    listed = client.get("/api/provents", params={"status": "ANNOUNCED"}).json()
    assert [(p["ticker"], p["type"], p["net_amount"]) for p in listed] == [("HGLG11", "INCOME", "2.20")]


def test_source_failure_is_recorded_and_app_keeps_working(client, market):
    _seed(client)
    market(PRICES, fail=True)
    res = client.post("/api/market-data/refresh").json()
    assert res["errors"]
    status = {s["source"]: s for s in client.get("/api/data-sources").json()}
    assert status["prices"]["ok"] is False
    assert status["ibov"]["ok"] is False
    # No quotes yet: positions are still served, valued at cost
    summary = client.get("/api/portfolio/summary").json()
    assert summary["market_value"] == "700.00"

    market(PRICES)
    assert client.post("/api/market-data/refresh").json()["errors"] == []
    status = {s["source"]: s for s in client.get("/api/data-sources").json()}
    assert status["prices"]["ok"] is True
    assert status["prices"]["last_success_at"] is not None


def test_positions_without_prices_fall_back_to_cost(client):
    _seed(client)
    summary = client.get("/api/portfolio/summary").json()
    assert summary["market_value"] == "700.00"
    assert sorted(summary["missing_prices"]) == ["HGLG11", "WEGE3"]


def test_unadjust_rebuilds_raw_close_before_a_split():
    adjusted = pd.Series(
        [28.0, 27.9, 27.97], index=pd.to_datetime(["2024-04-15", "2024-04-16", "2024-04-17"])
    )
    splits = pd.Series([2.0], index=pd.to_datetime(["2024-04-16"]))
    assert unadjust(adjusted, splits).tolist() == [56.0, 27.9, 27.97]


def _bcb(handler):
    return BCBRatesProvider(httpx.Client(transport=httpx.MockTransport(handler)), backoff=0)


def test_sgs_gateway_errors_are_retried():
    calls = []

    def flaky(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(502)
        return httpx.Response(200, json=[{"data": "01/10/2026", "valor": "0.055131"}])

    assert _bcb(flaky).cdi_daily(date(2026, 10, 1), date(2026, 10, 1)) == [(date(2026, 10, 1), D("0.055131"))]
    assert len(calls) == 3

    calls.clear()
    with pytest.raises(MarketDataError, match="BCB respondeu 502"):
        _bcb(lambda r: calls.append(r) or httpx.Response(502)).cdi_daily(date(2026, 10, 1), date(2026, 10, 1))
    assert len(calls) == 3

    calls.clear()
    with pytest.raises(MarketDataError, match="BCB respondeu 400"):
        _bcb(lambda r: calls.append(r) or httpx.Response(400)).cdi_daily(date(2026, 10, 1), date(2026, 10, 1))
    assert len(calls) == 1


def test_sgs_not_found_with_http_200_means_no_new_data():
    # Real answer for 10/10 → 13/10/2026 (weekend + holiday + today not yet published)
    body = (Path(__file__).parent / "fixtures" / "bcb" / "sgs12_not_found_200.json").read_bytes()
    assert (
        _bcb(lambda r: httpx.Response(200, content=body)).cdi_daily(date(2026, 10, 10), date(2026, 10, 13))
        == []
    )
    assert (
        _bcb(lambda r: httpx.Response(404, content=body)).cdi_daily(date(2026, 10, 13), date(2026, 10, 13))
        == []
    )


def test_sgs_other_errors_raise():
    with pytest.raises(MarketDataError, match="formato inesperado"):
        _bcb(lambda r: httpx.Response(200, json="oops")).cdi_daily(date(2026, 10, 1), date(2026, 10, 2))
    with pytest.raises(MarketDataError, match="BCB respondeu erro"):
        error = {"erro": {"statusCode": 500, "detail": "boom"}}
        _bcb(lambda r: httpx.Response(200, json=error)).cdi_daily(date(2026, 10, 1), date(2026, 10, 2))


def test_parse_sgs_real_response():
    payload = json.loads((Path(__file__).parent / "fixtures" / "bcb" / "sgs12_sample.json").read_text())
    rows = parse_sgs(payload)
    assert rows[0] == (date(2026, 9, 25), D("0.050788"))
