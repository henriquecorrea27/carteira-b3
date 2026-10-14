"""F6 — rule engine (rules_config/stocks.yaml, v2). Closed cases for scoring, statuses and the decision table."""

import copy
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
from app.rules.engine import IMPLAUSIBLE, Decision, Status, evaluate, load_rules, score_fraction

RAW = Path(__file__).parent / "fixtures" / "cvm" / "raw"
UNITS = {"pe": "x", "pb": "x", "ev_ebit": "x", "net_debt_ebitda": "x", "current_ratio": "x", "bvps": "brl",
         "daily_liquidity": "brl", "graham_price": "brl", "bazin_price": "brl", "market_cap": "brl", "eps": "brl",
         "dps_5y": "brl", "cash_conversion_5y": "x", "earnings_drops_5y": "count", "pe_norm": "x",
         "ev_ebit_norm": "x", "net_debt_ebitda_norm": "x"}  # fmt: skip

# A company that maxes every indicator
GREAT = {
    "roe_5y": "0.25", "roic": "0.20", "net_margin_5y": "0.20", "cagr_earnings_5y": "0.20", "net_debt_ebitda": "0.2",
    "cagr_revenue_5y": "0.16", "current_ratio": "2", "payout_5y": "0.5", "cash_conversion_5y": "1.2",
    "earnings_drops_5y": "0", "cagr_book_5y": "0.15", "equity_to_assets": "0.12", "graham_margin": "0.4",
    "pe": "5", "ev_ebit": "4", "dy_5y": "0.11", "pb": "0.7", "fcf_yield": "0.12", "pe_norm": "5", "ev_ebit_norm": "4",
    "net_debt_ebitda_norm": "0.2", "eps": "2", "bvps": "10", "daily_liquidity": "50000000",
}  # fmt: skip


def fundamentals_result(
    sector=None,
    profitable=5,
    years=5,
    notes=None,
    invalid=(),
    template="INDUSTRIAL",
    issuer=None,
    issuer_status="FASE OPERACIONAL",
    as_of=None,
    last_dfp=date(2025, 12, 31),
    last_itr=date(2026, 6, 30),
    **values,
):
    data = {**GREAT, **values}
    keys = set(GREAT) | {"graham_price", "bazin_price", "market_cap", "dps_5y"}
    indicators = {}
    for key in keys:
        raw = data.get(key)
        value = None if raw is None else D(raw)
        indicators[key] = Indicator(
            key, key, value, UNITS.get(key, "pct"), (notes or {}).get(key), invalid=key in invalid
        )
    return FundamentalsResult(
        sector, indicators, profitable, years, last_dfp, last_itr, None,
        template=template, issuer=issuer, issuer_status=issuer_status, as_of=as_of,
    )  # fmt: skip


def by_key(analysis):
    return {i.key: i for i in analysis.indicators}


def weights(rules):
    return {r["key"]: r["weight"] for r in rules}


# --- configuration ----------------------------------------------------------------------------


def test_approved_weights_v2():
    """CLAUDE.md §5: weights approved by the owner on 10/10/2026 (analyst proposal v2) and the chart analysis
    specified on 13/10/2026 (v3); daily-liquidity eliminatory removed on 14/10/2026 (v4). Changing them needs
    an explicit decision — update this test, the YAML and CLAUDE.md together."""
    cfg = load_rules()
    assert cfg["version"] == 4
    assert list(cfg["eliminatory"]) == ["E1", "E2", "E3", "E5"]
    assert cfg["sectors"]["FINANCIAL"]["eliminatory"] == ["E1", "E2", "E5"]
    assert weights(cfg["quality"]) == {
        "roic": 20, "roe_5y": 10, "net_margin_5y": 5, "net_debt_ebitda": 20, "current_ratio": 5,
        "cagr_revenue_5y": 10, "cagr_earnings_5y": 10, "cash_conversion_5y": 10, "earnings_drops_5y": 5,
        "payout_5y": 5,
    }  # fmt: skip
    assert weights(cfg["price"]) == {
        "ev_ebit": 30, "pe": 20, "dy_5y": 20, "pb": 10, "fcf_yield": 20, "graham_margin": 0,
    }  # fmt: skip
    sectors = cfg["sectors"]
    assert weights(sectors["FINANCIAL"]["quality"]) == {
        "roe_5y": 45, "cagr_earnings_5y": 20, "cagr_book_5y": 15, "equity_to_assets": 10, "payout_5y": 10,
    }  # fmt: skip
    assert weights(sectors["FINANCIAL"]["price"]) == {"pe": 40, "dy_5y": 40, "pb": 20}
    assert weights(sectors["UTILITY"]["price"]) == {
        "dy_5y": 35,
        "ev_ebit": 25,
        "pe": 20,
        "pb": 10,
        "fcf_yield": 10,
    }
    assert weights(sectors["CYCLICAL"]["price"]) == {"pe_norm": 25, "ev_ebit_norm": 25, "dy_5y": 30, "pb": 20}
    for group in ("quality", "price"):
        assert sum(weights(cfg[group]).values()) == 100
        for name, sector in sectors.items():
            assert sum(weights(sector[group]).values()) == 100, (name, group)
    assert cfg["decision"]["final_weights"] == {"quality": 0.6, "price": 0.4}
    assert cfg["technical"] == {
        "enabled": True,
        "weight": 0.25,
        "sma_days": 200,
        "cheap": -0.10,
        "expensive": 0.10,
    }


# --- scoring ----------------------------------------------------------------------------------


def test_linear_scoring_both_directions_and_clamp():
    roe = {"bad": 0.08, "good": 0.20}
    assert score_fraction(roe, 0.14) == pytest.approx(0.5)
    assert score_fraction(roe, 0.30) == 1.0
    assert score_fraction(roe, 0.02) == 0.0
    pe = {"bad": 20, "good": 7}  # lower is better
    assert score_fraction(pe, 13.5) == pytest.approx(0.5)
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
    # ROIC 11% → half of 20 ; P/L 13,5 → half of 20 ; everything else maxed
    a = evaluate(fundamentals_result(roic="0.11", pe="13.5"))
    k = by_key(a)
    assert k["roic"].points == pytest.approx(10)
    assert k["roic"].status == Status.MID
    assert k["pe"].points == pytest.approx(10)
    assert k["roe_5y"].status == Status.GOOD
    assert a.score_quality == 90.0
    assert a.score_price == 90.0
    assert a.score_final == 90.0  # 0,6 × 90 + 0,4 × 90
    assert k["roic"].range_label == "6% → 16%"
    assert k["pe"].range_label == "20 → 7"
    assert k["payout_5y"].range_label == "ótimo 25%–80%"
    assert k["earnings_drops_5y"].range_label == "3 → 0"


def test_final_score_weights_quality_more():
    a = evaluate(fundamentals_result(pe="20", ev_ebit="15", dy_5y="0.02", pb="3", fcf_yield="0.02"))
    assert (a.score_quality, a.score_price) == (100.0, 0.0)
    assert a.score_final == 60.0


def test_graham_is_shown_but_weighs_nothing():
    a = evaluate(fundamentals_result(graham_margin="-0.5"))
    g = by_key(a)["graham_margin"]
    assert (g.weight, g.points, g.status) == (0, 0.0, Status.BAD)
    assert a.score_price == 100.0


def test_missing_indicator_leaves_the_denominator():
    a = evaluate(fundamentals_result(roic=None, notes={"roic": "dado indisponível"}))
    k = by_key(a)
    assert (k["roic"].points, k["roic"].status, k["roic"].note) == (None, Status.NA, "dado indisponível")
    assert a.score_quality == 100.0  # 80 / 80
    assert not a.quality_inconclusive


def test_invalid_value_scores_zero_when_the_rule_says_so():
    # CAGR lucro with a final loss: 0 of 10 (stays in the denominator), not "no data"
    a = evaluate(fundamentals_result(cagr_earnings_5y=None, invalid={"cagr_earnings_5y"}))
    k = by_key(a)["cagr_earnings_5y"]
    assert (k.points, k.status) == (0.0, Status.BAD)
    assert a.score_quality == 90.0
    # FCO / lucro has no `if_invalid: zero`: an invalid value is just missing
    b = evaluate(fundamentals_result(cash_conversion_5y=None, invalid={"cash_conversion_5y"}))
    assert by_key(b)["cash_conversion_5y"].points is None
    assert b.score_quality == 100.0


def test_loss_caps_the_price_score():
    # LPA ≤ 0: P/L invalid (0 of 20) → fundamental price 80, capped at 40 → never COMPRAR
    a = evaluate(fundamentals_result(pe=None, eps="-1", invalid={"pe"}))
    assert a.score_price_fundamental == 80.0
    assert a.score_price == 40.0
    assert a.decision == Decision.WAIT
    assert any("limitada a 40" in w for w in a.warnings)


def test_implausible_values_are_ignored_with_a_warning():
    a = evaluate(fundamentals_result(pe="0.8", pb="0.05"))
    k = by_key(a)
    assert (k["pe"].points, k["pe"].status, k["pe"].note) == (None, Status.NA, IMPLAUSIBLE)
    assert k["pb"].points is None
    assert a.score_price == 100.0  # 70 / 70
    assert a.warnings.count(IMPLAUSIBLE) == 1
    assert by_key(evaluate(fundamentals_result(dy_5y="0.30")))["dy_5y"].note == IMPLAUSIBLE
    assert by_key(evaluate(fundamentals_result(ev_ebit="0.3")))["ev_ebit"].note == IMPLAUSIBLE
    assert by_key(evaluate(fundamentals_result(ev_ebit="-2")))["ev_ebit"].points == 30  # EV < 0: net cash


def test_rules_for_indicators_not_computed_are_skipped():
    cfg = copy.deepcopy(load_rules())
    cfg["quality"].append({"key": "not_implemented", "label": "x", "bad": 0, "good": 1, "weight": 50})
    a = evaluate(fundamentals_result(roic="0.11"), cfg)
    assert "not_implemented" not in by_key(a)
    assert a.score_quality == 90.0
    assert not a.quality_inconclusive


# --- decision table (§5.5) --------------------------------------------------------------------


def test_buy_when_quality_and_price_are_high():
    a = evaluate(fundamentals_result())
    assert a.decision == Decision.BUY
    assert "a favor" in a.main_reason


def test_wait_when_good_company_is_expensive():
    a = evaluate(fundamentals_result(pe="30", pb="4", ev_ebit="20", fcf_yield="0.01", graham_margin="-0.5"))
    assert a.score_quality >= 70 and a.score_price < 60
    assert a.decision == Decision.WAIT
    assert a.main_reason.startswith("EV/EBIT 20,00 contra")


def test_wait_when_quality_between_50_and_70():
    # ROIC (20) + Dív/EBITDA (20) + ROE (10) at zero → 50
    a = evaluate(fundamentals_result(roic="0", net_debt_ebitda="3.0", roe_5y="0"))
    assert a.score_quality == 50.0
    assert a.decision == Decision.WAIT


def test_avoid_when_quality_below_50():
    a = evaluate(fundamentals_result(roic="0", net_debt_ebitda="3.0", roe_5y="0", current_ratio="0.5"))
    assert a.score_quality == 45.0
    assert a.decision == Decision.AVOID


@pytest.mark.parametrize(
    ("kwargs", "failed"),
    [
        ({"profitable": 3}, "E1"),
        ({"bvps": "-1"}, "E2"),
        ({"net_debt_ebitda": "3.6"}, "E3"),
        ({"issuer_status": "EM RECUPERAÇÃO JUDICIAL OU EQUIVALENTE"}, "E5"),
        ({"issuer_status": "FALIDA"}, "E5"),
        ({"issuer": "AMBP"}, "E5"),  # manual list: judicial recovery not yet in the CVM registry
    ],
)
def test_any_failed_eliminatory_means_avoid_and_caps_the_score(kwargs, failed):
    a = evaluate(fundamentals_result(**kwargs))
    assert a.decision == Decision.AVOID
    assert [c.id for c in a.eliminatory if c.passed is False] == [failed]
    assert a.main_reason.startswith({c.id: c.label for c in a.eliminatory}[failed])
    assert a.score_final == 30.0  # would be ~100 without the veto cap


def test_low_liquidity_no_longer_eliminates():
    # E4 (daily liquidity ≥ R$ 2 mi) was removed on 14/10/2026: the liquidity is shown, never a veto
    a = evaluate(fundamentals_result(daily_liquidity="150000"))
    assert "E4" not in {c.id for c in a.eliminatory}
    assert a.decision == Decision.BUY


def test_e5_without_registry_data_does_not_eliminate():
    a = evaluate(fundamentals_result(issuer_status=None))
    assert {c.id: c.passed for c in a.eliminatory}["E5"] is None
    assert a.decision == Decision.BUY


def test_negative_ebitda_fails_e3_but_missing_data_does_not():
    neg = evaluate(
        fundamentals_result(
            net_debt_ebitda=None, notes={"net_debt_ebitda": "EBITDA negativo"}, invalid={"net_debt_ebitda"}
        )
    )
    assert {c.id: c.passed for c in neg.eliminatory}["E3"] is False
    assert by_key(neg)["net_debt_ebitda"].points == 0.0
    unknown = evaluate(
        fundamentals_result(net_debt_ebitda=None, notes={"net_debt_ebitda": "D&A não localizada"})
    )
    assert {c.id: c.passed for c in unknown.eliminatory}["E3"] is None
    assert unknown.decision == Decision.BUY


def test_utilities_have_their_own_rules_and_debt_limit():
    a = evaluate(fundamentals_result(sector="UTILITY", net_debt_ebitda="4.0"))
    e3 = {c.id: c for c in a.eliminatory}["E3"]
    assert (e3.passed, e3.rule) == (True, "≤ 4,5")
    k = by_key(a)
    assert k["net_debt_ebitda"].range_label == "4,5 → 2"
    assert k["net_debt_ebitda"].points == pytest.approx(5)  # (4,5 − 4,0) / 2,5 × 25
    assert [i.key for i in a.indicators if i.group == "PRICE"] == [
        "dy_5y",
        "ev_ebit",
        "pe",
        "pb",
        "fcf_yield",
    ]


def test_cyclicals_use_five_year_averages():
    a = evaluate(fundamentals_result(sector="CYCLICAL", net_debt_ebitda="1.0", net_debt_ebitda_norm="3.2"))
    e3 = {c.id: c for c in a.eliminatory}["E3"]
    assert (e3.passed, e3.rule, e3.value_label) == (False, "≤ 3,0", "3,20 (EBITDA médio 5a)")
    b = evaluate(fundamentals_result(sector="CYCLICAL"))
    assert [i.key for i in b.indicators if i.group == "PRICE"] == ["pe_norm", "ev_ebit_norm", "dy_5y", "pb"]
    assert "cagr_earnings_5y" not in by_key(b)
    assert "setor cíclico — múltiplos sobre lucro médio de 5 anos" in b.warnings


def test_more_than_30_percent_missing_is_inconclusive_and_waits():
    # ROIC (20) + Dív/EBITDA (20) missing = 40% of the quality weight
    a = evaluate(fundamentals_result(roic=None, net_debt_ebitda=None))
    assert a.quality_inconclusive
    assert a.decision == Decision.WAIT
    assert any("inconclusiva" in w for w in a.warnings)


def test_financial_sector_uses_its_own_set():
    a = evaluate(fundamentals_result(sector="FINANCIAL", template="BANK"))
    assert [i.key for i in a.indicators] == [
        "roe_5y", "cagr_earnings_5y", "cagr_book_5y", "equity_to_assets", "payout_5y", "pe", "dy_5y", "pb",
    ]  # fmt: skip
    assert [c.id for c in a.eliminatory] == ["E1", "E2", "E5"]
    assert "análise parcial — setor financeiro" in a.warnings
    assert a.decision == Decision.BUY
    # Insurers (regular chart of accounts): PL / ativo total does not apply
    insurer = evaluate(fundamentals_result(sector="FINANCIAL", template="INDUSTRIAL", roe_5y="0.15"))
    assert "equity_to_assets" not in by_key(insurer)
    assert insurer.score_quality == 75.0  # (90 − 22,5) / 90: ROE 15% earns half of 45


def test_few_years_of_history():
    # Only 4 DFPs with 3 profitable: same tolerance as "4 of 5"
    a = evaluate(fundamentals_result(profitable=3, years=4))
    assert {c.id: c.passed for c in a.eliminatory}["E1"] is True
    b = evaluate(fundamentals_result(profitable=2, years=2))
    assert {c.id: c.passed for c in b.eliminatory}["E1"] is None


def test_stale_statements_make_the_scores_inconclusive():
    fresh = evaluate(fundamentals_result(as_of=date(2026, 10, 10)))
    assert not fresh.stale and fresh.decision == Decision.BUY
    old = evaluate(fundamentals_result(as_of=date(2027, 3, 1)))  # balance of 30/06/2026 + 8 months
    assert old.stale and old.quality_inconclusive and old.price_inconclusive
    assert old.decision == Decision.WAIT
    assert "dados contábeis defasados: último balanço de 30/06/2026" in old.warnings
    no_dfp = evaluate(
        fundamentals_result(as_of=date(2026, 6, 1), last_dfp=date(2024, 12, 31), last_itr=date(2026, 3, 31))
    )
    assert "dados contábeis defasados: sem DFP de 2025" in no_dfp.warnings


def test_technical_component_blends_into_the_price_score():
    base = fundamentals_result(pe="13.5")  # fundamental price 90
    a = evaluate(base, technical=40)
    assert (a.score_price_fundamental, a.score_technical, a.technical_weight) == (90.0, 40, 0.25)
    assert a.score_price == 77.5  # 0,75 × 90 + 0,25 × 40
    assert evaluate(base).score_price == 90.0  # not computed (short history) → w = 0
    cfg = copy.deepcopy(load_rules())
    cfg["technical"]["enabled"] = False
    assert evaluate(base, cfg, technical=40).score_price == 90.0


def test_technical_never_saves_a_vetoed_stock_nor_lifts_the_loss_cap():
    vetoed = evaluate(fundamentals_result(profitable=3), technical=100)
    assert vetoed.decision == Decision.AVOID and vetoed.score_final <= 30
    loss = evaluate(fundamentals_result(eps="-1", pe=None, invalid=("pe",)), technical=100)
    assert loss.score_price <= 40


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
    assert {e["id"] for e in body["eliminatory"]} == {"E1", "E2", "E3", "E5"}
    assert len(body["indicators"]) == 13
    assert all({"range_label", "points", "status", "weight"} <= set(i) for i in body["indicators"])
    assert body["last_dfp"] == "2025-12-31"
    v = body["valuation"]
    assert v["eps"] is not None and v["bvps"] is not None and v["shares"] is not None
    assert len(v["dps_by_year"]) == 5
    # Indicator panel (scored or not) and the history by year, oldest first
    keys = {f["key"] for f in body["fundamentals"]}
    assert {"pe", "ev_ebitda", "dy_12m", "roa", "net_debt_equity", "daily_liquidity"} <= keys
    labels = [h["label"] for h in body["history"]]
    assert labels[-1] == "12M" and labels[:-1] == sorted(labels[:-1])
    assert body["history"][-2]["revenue"] is not None
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
