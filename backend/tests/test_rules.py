"""F6 — rule engine (rules_config/stocks.yaml). Closed cases for scoring, statuses and the decision table."""

import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.api.corporate_events import get_events_source
from app.api.portfolio import get_market_provider
from app.fundamentals import service as fundamentals
from app.fundamentals.indicators import FundamentalsResult, Indicator
from app.main import app
from app.models import AnalysisSnapshot
from app.rules import service as rules
from app.rules.engine import Decision, Status, evaluate, load_rules, score_fraction

RAW = Path(__file__).parent / "fixtures" / "cvm" / "raw"
UNITS = {"pe": "x", "pb": "x", "ev_ebit": "x", "net_debt_ebitda": "x", "current_ratio": "x", "bvps": "brl",
         "daily_liquidity": "brl", "graham_price": "brl", "bazin_price": "brl", "market_cap": "brl", "eps": "brl",
         "dps_5y": "brl"}  # fmt: skip

# A company that maxes every indicator
GREAT = {
    "roe_5y": "0.25", "roic": "0.20", "net_margin_5y": "0.20", "cagr_earnings_5y": "0.15", "net_debt_ebitda": "0.2",
    "cagr_revenue_5y": "0.12", "current_ratio": "2", "payout_5y": "0.5", "graham_margin": "0.4", "pe": "6",
    "ev_ebit": "5", "dy_5y": "0.09", "pb": "0.9", "bvps": "10", "daily_liquidity": "50000000",
}  # fmt: skip


def fundamentals_result(sector=None, profitable=5, years=5, notes=None, **values):
    data = {**GREAT, **values}
    keys = set(GREAT) | {"eps", "graham_price", "bazin_price", "market_cap", "dps_5y"}
    indicators = {}
    for key in keys:
        raw = data.get(key)
        value = None if raw is None else D(raw)
        indicators[key] = Indicator(key, key, value, UNITS.get(key, "pct"), (notes or {}).get(key))
    return FundamentalsResult(
        sector, indicators, profitable, years, date(2025, 12, 31), date(2026, 6, 30), None
    )


def by_key(analysis):
    return {i.key: i for i in analysis.indicators}


# --- configuration ----------------------------------------------------------------------------


def test_weights_are_all_equal_while_under_evaluation():
    """CLAUDE.md §5: all weights are equal until the owner decides otherwise (update this test then)."""
    cfg = load_rules()
    assert {r["weight"] for r in cfg["quality"]} == {12.5}
    assert {r["weight"] for r in cfg["price"]} == {20}
    assert cfg["decision"]["final_weights"] == {"quality": 0.5, "price": 0.5}


# --- scoring ----------------------------------------------------------------------------------


def test_linear_scoring_both_directions_and_clamp():
    roe = {"bad": 0.08, "good": 0.20}
    assert score_fraction(roe, 0.14) == pytest.approx(0.5)
    assert score_fraction(roe, 0.30) == 1.0
    assert score_fraction(roe, 0.02) == 0.0
    pe = {"bad": 25, "good": 8}  # lower is better
    assert score_fraction(pe, 16.5) == pytest.approx(0.5)
    assert score_fraction(pe, 4) == 1.0
    debt = {"bad": 3.0, "good": 0.5}
    assert score_fraction(debt, -1.0) == 1.0  # net cash is great


def test_payout_band():
    band = {"band": [0.0, 0.25, 0.80, 1.0]}
    assert score_fraction(band, 0.50) == 1.0
    assert score_fraction(band, 0.125) == pytest.approx(0.5)
    assert score_fraction(band, 0.90) == pytest.approx(0.5)
    assert score_fraction(band, 1.2) == 0.0
    assert score_fraction(band, -0.1) == 0.0


def test_scores_points_and_statuses():
    # ROE 14% → half of 12,5 ; P/L 16,5 → half of 20 ; everything else maxed
    a = evaluate(fundamentals_result(roe_5y="0.14", pe="16.5"))
    k = by_key(a)
    assert k["roe_5y"].points == pytest.approx(6.25)
    assert k["roe_5y"].status == Status.MID
    assert k["pe"].points == pytest.approx(10)
    assert k["roic"].status == Status.GOOD
    assert a.score_quality == pytest.approx(93.8)  # (100 − 6,25) / 100
    assert a.score_price == pytest.approx(90.0)  # (100 − 10) / 100
    assert a.score_final == pytest.approx(91.9)
    assert k["roe_5y"].range_label == "8% → 20%"
    assert k["pe"].range_label == "25 → 8"
    assert k["payout_5y"].range_label == "ótimo 25%–80%"


def test_missing_indicator_leaves_the_denominator():
    a = evaluate(fundamentals_result(roic=None, notes={"roic": "dado indisponível"}))
    k = by_key(a)
    assert (k["roic"].points, k["roic"].status, k["roic"].note) == (None, Status.NA, "dado indisponível")
    assert a.score_quality == 100.0  # 87,5 / 87,5
    assert not a.quality_inconclusive


# --- decision table (§5.5) --------------------------------------------------------------------


def test_buy_when_quality_and_price_are_high():
    a = evaluate(fundamentals_result())
    assert a.decision == Decision.BUY
    assert "a favor" in a.main_reason


def test_wait_when_good_company_is_expensive():
    a = evaluate(fundamentals_result(pe="30", pb="4", ev_ebit="20", graham_margin="-0.5"))
    assert a.score_quality >= 70 and a.score_price < 60
    assert a.decision == Decision.WAIT
    assert "contra" in a.main_reason


def test_wait_when_quality_between_50_and_70():
    # 4 of 8 quality indicators at zero → 50
    a = evaluate(fundamentals_result(roe_5y="0", roic="0", net_margin_5y="0", cagr_earnings_5y="-0.1"))
    assert a.score_quality == 50.0
    assert a.decision == Decision.WAIT


def test_avoid_when_quality_below_50():
    a = evaluate(
        fundamentals_result(
            roe_5y="0", roic="0", net_margin_5y="0", cagr_earnings_5y="-0.1", current_ratio="0.5"
        )
    )
    assert a.score_quality < 50
    assert a.decision == Decision.AVOID


@pytest.mark.parametrize(
    ("kwargs", "failed"),
    [
        ({"profitable": 3}, "E1"),
        ({"bvps": "-1"}, "E2"),
        ({"net_debt_ebitda": "3.6"}, "E3"),
        ({"daily_liquidity": "1999999"}, "E4"),
    ],
)
def test_any_failed_eliminatory_means_avoid(kwargs, failed):
    a = evaluate(fundamentals_result(**kwargs))
    assert a.decision == Decision.AVOID
    assert [c.id for c in a.eliminatory if c.passed is False] == [failed]
    assert a.main_reason.startswith({c.id: c.label for c in a.eliminatory}[failed])


def test_negative_ebitda_fails_e3_but_missing_data_does_not():
    neg = evaluate(fundamentals_result(net_debt_ebitda=None, notes={"net_debt_ebitda": "EBITDA negativo"}))
    assert {c.id: c.passed for c in neg.eliminatory}["E3"] is False
    unknown = evaluate(
        fundamentals_result(net_debt_ebitda=None, notes={"net_debt_ebitda": "D&A não localizada"})
    )
    assert {c.id: c.passed for c in unknown.eliminatory}["E3"] is None
    assert unknown.decision == Decision.BUY


def test_utilities_have_a_higher_debt_limit():
    a = evaluate(fundamentals_result(sector="UTILITY", net_debt_ebitda="4.0"))
    e3 = {c.id: c for c in a.eliminatory}["E3"]
    assert (e3.passed, e3.rule) == (True, "≤ 4,5")


def test_more_than_30_percent_missing_is_inconclusive_and_waits():
    # 3 of 8 quality indicators missing = 37,5% of the weight
    a = evaluate(fundamentals_result(roe_5y=None, roic=None, net_margin_5y=None))
    assert a.quality_inconclusive
    assert a.decision == Decision.WAIT
    assert any("inconclusiva" in w for w in a.warnings)


def test_financial_sector_uses_the_reduced_set():
    a = evaluate(
        fundamentals_result(
            sector="FINANCIAL", roic=None, net_debt_ebitda=None, current_ratio=None, ev_ebit=None
        )
    )
    assert [i.key for i in a.indicators] == ["roe_5y", "cagr_earnings_5y", "payout_5y", "pe", "dy_5y", "pb"]
    assert [c.id for c in a.eliminatory] == ["E1", "E2", "E4"]
    assert "análise parcial — setor financeiro" in a.warnings
    assert a.decision == Decision.BUY


def test_few_years_of_history():
    # Only 4 DFPs with 3 profitable: same tolerance as "4 of 5"
    a = evaluate(fundamentals_result(profitable=3, years=4))
    assert {c.id: c.passed for c in a.eliminatory}["E1"] is True
    b = evaluate(fundamentals_result(profitable=2, years=2))
    assert {c.id: c.passed for c in b.eliminatory}["E1"] is None


# --- service and API --------------------------------------------------------------------------


class FakeMarket:
    name = "fake"

    def daily_bars(self, tickers, start, end):
        from app.market_data.base import DailyBar

        out = {}
        for t in tickers:
            close = {"CMIG4": D("12"), "CMIG3": D("13")}.get(t)
            if close:
                days = [date(2026, 10, d) for d in (6, 7, 8) if start <= date(2026, 10, d) <= end]
                out[t] = [DailyBar(d, close, close, D(10_000_000), close, close + 1, close - 1) for d in days]
        return out

    def index_closes(self, symbol, start, end):
        return []


class FakeEvents:
    def supplement(self, issuer):
        return json.loads(
            (Path(__file__).parent / "fixtures" / "b3_events" / f"{issuer}_supplement.json").read_text(
                "utf-8"
            )
        )


@pytest.fixture
def ingested(session_factory):
    with session_factory() as session:
        fundamentals.ingest(session, today=date(2026, 10, 8), download=False, raw=RAW)
    app.dependency_overrides[get_market_provider] = lambda: FakeMarket()
    app.dependency_overrides[get_events_source] = lambda: FakeEvents()
    return session_factory


def test_analysis_endpoint_explains_the_decision(client, ingested):
    res = client.get("/api/analysis/cmig4")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ticker"] == "CMIG4"
    assert body["decision"] in ("BUY", "WAIT", "AVOID")
    assert body["special_sector"] == "UTILITY"
    assert {e["id"] for e in body["eliminatory"]} == {"E1", "E2", "E3", "E4"}
    assert len(body["indicators"]) == 13
    assert all({"range_label", "points", "status", "weight"} <= set(i) for i in body["indicators"])
    assert body["last_dfp"] == "2025-12-31"
    with ingested() as session:
        snaps = session.query(AnalysisSnapshot).all()
        assert [(s.ticker, s.decision) for s in snaps] == [("CMIG4", body["decision"])]
        assert snaps[0].details["indicators"]


def test_analysis_unknown_ticker(client, ingested):
    res = client.get("/api/analysis/HGLG11")
    assert res.status_code == 404
    assert "FIIs" in res.json()["detail"]


def test_portfolio_run_and_positions_show_the_decision(client, ingested):
    client.post(
        "/api/transactions",
        json={"date": "2026-01-05", "ticker": "CMIG4", "type": "BUY", "quantity": "100", "price": "10"},
    )
    client.post(
        "/api/transactions",
        json={"date": "2026-01-05", "ticker": "HGLG11", "type": "BUY", "quantity": "1", "price": "150"},
    )
    run = client.post("/api/analysis/portfolio").json()
    assert (run["analyzed"], run["skipped"]) == (["CMIG4"], ["HGLG11"])
    positions = {p["ticker"]: p for p in client.get("/api/portfolio/positions").json()}
    assert positions["CMIG4"]["rules"]["decision"] in ("BUY", "WAIT", "AVOID")
    assert positions["HGLG11"]["rules"] is None


def test_decision_changes_compare_with_the_previous_snapshot(session_factory):
    with session_factory() as session:
        for day, decision in (
            (date(2026, 10, 6), "WAIT"),
            (date(2026, 10, 7), "WAIT"),
            (date(2026, 10, 8), "BUY"),
        ):
            session.add(
                AnalysisSnapshot(ticker="CMIG4", date=day, decision=decision, rules_version=1, details={})
            )
        session.commit()
        changes = rules.decision_changes(session, date(2026, 10, 8))
        assert [(c.ticker, c.previous, c.current) for c in changes] == [("CMIG4", "WAIT", "BUY")]
        assert rules.decision_changes(session, date(2026, 10, 7)) == []


def test_price_bars_endpoint(client, ingested):
    bars = client.get("/api/prices/CMIG4").json()
    assert [b["close"] for b in bars] == ["12", "12", "12"]
    assert bars[0]["high"] == "13"
