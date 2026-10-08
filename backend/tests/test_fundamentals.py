"""F5 — CVM ingestion and indicators. Extraction is checked against REAL public filings
(fixtures/cvm/raw, cut by make_cvm_fixtures.py); indicator formulas against closed numeric cases."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.fundamentals import service
from app.fundamentals.cvm_parser import CapitalComposition, parse_capital, parse_document
from app.fundamentals.indicators import compute, special_sector
from app.fundamentals.shares import ShareCount, from_b3, from_cvm
from app.market_data.base import DailyBar

RAW = Path(__file__).parent / "fixtures" / "cvm" / "raw"
B3 = Path(__file__).parent / "fixtures" / "b3_events"
CEMIG, BBAS, GOAU = "17.155.730/0001-64", "00.000.000/0001-91", "92.690.783/0001-09"


def periods_of(cnpj, file, doc):
    return [p for p in parse_document(RAW / file, doc) if p.cnpj == cnpj]


# --- extraction from real filings ---------------------------------------------------------------


def test_cemig_dfp_2025_key_accounts():
    (p,) = periods_of(CEMIG, "dfp_cia_aberta_2025.zip", "DFP")
    f = p.figures
    assert (p.period_end, p.consolidated, f.template) == (date(2025, 12, 31), True, "INDUSTRIAL")
    # Values published in thousands (ESCALA_MOEDA = MIL) are stored in R$
    assert f.revenue == D("42751283000")
    assert f.ebit == D("6750308000")
    assert f.net_income_controlling == D("4897409000")  # 3.11.01, excludes minority interest
    assert f.equity_controlling == D("28576380000")  # 2.03 − 2.03.09 (non-controlling)
    assert f.gross_debt == D("19465331000")  # loans + debentures, no leases
    assert f.cash == D("2661338000")  # cash + short-term investments
    assert f.d_and_a == D("1533416000")
    assert f.missing == []


def test_bank_template_uses_its_own_accounts():
    (p,) = periods_of(BBAS, "dfp_cia_aberta_2025.zip", "DFP")
    f = p.figures
    assert f.template == "BANK"
    assert f.equity_controlling == D("189207675000")  # 2.07.01
    assert f.current_assets is None and f.gross_debt is None
    assert f.net_income_controlling is not None


def test_holding_dividends_come_from_the_parent_only_cash_flow():
    (p,) = periods_of(GOAU, "dfp_cia_aberta_2025.zip", "DFP")
    # Consolidated cash flow also has what Gerdau S.A. pays to its own minority shareholders
    assert 0 < p.figures.dividends_paid < p.figures.net_income_controlling * 2


def test_itr_yields_year_to_date_and_prior_year_comparative():
    rows = periods_of(CEMIG, "itr_cia_aberta_2026.zip", "ITR")
    by_end = {(r.period_end, r.comparative): r for r in rows}
    q2 = by_end[(date(2026, 6, 30), False)]
    prior = by_end[(date(2025, 6, 30), True)]
    assert q2.period_start == date(2026, 1, 1)  # year-to-date, not the quarter alone
    assert q2.figures.revenue == D("21618781000")
    assert prior.figures.revenue == D("20630526000")
    assert prior.figures.equity is None  # comparatives carry flows only


def test_capital_composition_has_no_scale_column():
    comp = {c.cnpj: c for c in parse_capital(RAW / "dfp_cia_aberta_2025.zip", "DFP")}
    assert comp[CEMIG].on == D("956602")  # thousands
    assert comp[BBAS].on == D("5730834040")  # units


# --- share counts -------------------------------------------------------------------------------


def test_b3_share_counts_are_primary():
    payload = json.loads((B3 / "CMIG_supplement.json").read_text("utf-8"))
    previous = ShareCount(D(0), D(0), D(0), D("1100000"), "CVM", None)
    count = from_b3(payload, previous, date(2026, 10, 8))
    assert (count.on, count.pn, count.source) == (D("956601911"), D("1905179984"), "B3")
    assert count.outstanding == D("2860681895")


def test_cvm_fallback_infers_thousands_from_eps():
    comp = CapitalComposition(CEMIG, date(2025, 12, 31), D("956602"), D("1905180"), D(0), D("1100"))
    count = from_cvm(comp, net_income=D("4897409000"), eps=D("1.71"))
    assert count.on == D("956602000")
    assert count.treasury_pn == D("1100000")
    units = from_cvm(
        CapitalComposition(BBAS, date(2025, 12, 31), D("5730834040"), D(0), D(0), D(0)),
        D("13698124000"),
        D("2.40"),
    )
    assert units.on == D("5730834040")


# --- indicator formulas (closed numeric cases) --------------------------------------------------


@dataclass
class P:
    doc_type: str
    period_end: date
    period_start: date | None = None
    comparative: bool = False
    received_on: date | None = None
    revenue: D | None = None
    ebit: D | None = None
    net_income: D | None = None
    net_income_controlling: D | None = None
    d_and_a: D | None = None
    dividends_paid: D | None = None
    current_assets: D | None = None
    current_liabilities: D | None = None
    cash: D | None = None
    gross_debt: D | None = None
    equity: D | None = None
    equity_controlling: D | None = None


def annual(year, ni, rev, eq, div, ebit=None, da=None):
    return P("DFP", date(year, 12, 31), date(year, 1, 1), revenue=D(rev), net_income_controlling=D(ni),
             equity=D(eq), equity_controlling=D(eq), dividends_paid=D(div), ebit=D(ebit or ni), d_and_a=D(da or 0),
             current_assets=D(300), current_liabilities=D(200), cash=D(100), gross_debt=D(400))  # fmt: skip


def company():
    # Net income 100 → 200 over 5 years (CAGR 14,87%), equity 1000 → 1500, dividends 50% of earnings
    years = [
        annual(2020, 100, 1000, 1000, 50),
        annual(2021, 120, 1100, 1100, 60),
        annual(2022, 140, 1200, 1200, 70),
        annual(2023, 160, 1300, 1300, 80),
        annual(2024, 180, 1400, 1400, 90),
        annual(2025, 200, 1500, 1500, 100, ebit=300, da=100),
    ]
    q2 = P("ITR", date(2026, 6, 30), date(2026, 1, 1), net_income_controlling=D(120), ebit=D(170), d_and_a=D(50),
           revenue=D(800), equity=D(1600), equity_controlling=D(1600), current_assets=D(330), current_liabilities=D(220),
           cash=D(150), gross_debt=D(450))  # fmt: skip
    q2_prior = P("ITR", date(2025, 6, 30), date(2025, 1, 1), comparative=True, net_income_controlling=D(90),
                 ebit=D(140), d_and_a=D(45), revenue=D(700))  # fmt: skip
    q2_prior_balance = P("ITR", date(2025, 6, 30), date(2025, 1, 1), net_income_controlling=D(90), ebit=D(140),
                         d_and_a=D(45), revenue=D(700), equity=D(1400), equity_controlling=D(1400))  # fmt: skip
    return [*years, q2, q2_prior, q2_prior_balance]


def run(price="23", **kw):
    shares = ShareCount(D(100), D(0), D(0), D(0), "B3", None)
    return compute(
        company(), shares, D(price), {"ON": D(price)}, D("5000000"), kw.get("sector"), "INDUSTRIAL"
    )


def test_ttm_is_ytd_plus_last_annual_minus_prior_ytd():
    r = run()
    # Net income TTM = 120 + 200 − 90 = 230 → LPA 2,30 ; P/L = 23 / 2,30 = 10
    assert r.value("eps") == D("2.3")
    assert r.value("pe") == D("10")
    # ROE = 230 / average(1600, 1400 a year earlier) = 230 / 1500
    assert r.value("roe").quantize(D("0.0001")) == D("0.1533")
    assert (r.last_dfp, r.last_itr) == (date(2025, 12, 31), date(2026, 6, 30))


def test_five_year_averages_and_cagr():
    r = run()
    assert r.value("cagr_earnings_5y").quantize(D("0.0001")) == D("0.1487")  # (200/100)^(1/5) − 1
    assert r.value("cagr_revenue_5y").quantize(D("0.0001")) == D("0.0845")  # (1500/1000)^(1/5) − 1
    assert r.value("payout_5y") == D("0.5")
    # Margins 120/1100 … 200/1500 averaged
    expected_margin = (
        sum(D(n) / D(v) for n, v in [(120, 1100), (140, 1200), (160, 1300), (180, 1400), (200, 1500)]) / 5
    )
    assert r.value("net_margin_5y") == expected_margin
    assert (r.profitable_years, r.years_available) == (5, 5)


def test_debt_valuation_and_graham():
    r = run()
    # EBITDA TTM = (170 + 300 − 140) + (50 + 100 − 45) = 330 + 105 = 435 ; net debt = 450 − 150 = 300
    assert r.value("net_debt_ebitda") == D(300) / D(435)
    assert r.value("current_ratio") == D("1.5")
    # ROIC = 330 × 0,66 / (1600 + 450 − 150)
    assert r.value("roic") == D(330) * D("0.66") / D(1900)
    assert r.value("market_cap") == D("2300")
    assert r.value("ev_ebit") == (D(2300) + D(300)) / D(330)
    assert r.value("bvps") == D(16)
    assert r.value("pb") == D(23) / D(16)
    # Graham = √(22,5 × 2,3 × 16) = √828 = 28,775
    assert r.value("graham_price").quantize(D("0.001")) == D("28.775")
    # DPS 5 years: (60+70+80+90+100)/5/100 shares = 0,80 → DY = 0,8/23 ; Bazin = 0,8 / 0,06
    assert r.value("dps_5y") == D("0.8")
    assert r.value("bazin_price").quantize(D("0.01")) == D("13.33")


def test_negative_eps_disables_pe_and_graham():
    data = company()
    data[-3].net_income_controlling = D(-500)  # loss in 2026 YTD
    r = compute(
        data, ShareCount(D(100), D(0), D(0), D(0), "B3", None), D(23), {"ON": D(23)}, None, None, None
    )
    assert r.value("pe") is None
    assert r.indicators["pe"].note == "LPA ≤ 0"
    assert r.value("graham_price") is None


@pytest.mark.parametrize(
    ("sector", "template", "expected"),
    [
        ("Bancos", "BANK", "FINANCIAL"),
        ("Emp. Adm. Part. - Seguradoras e Corretoras", "INDUSTRIAL", "FINANCIAL"),
        ("Emp. Adm. Part. - Intermediação Financeira", "INDUSTRIAL", "FINANCIAL"),
        ("Energia Elétrica", "INDUSTRIAL", "UTILITY"),
        ("Saneamento, Serv. Água e Gás", "INDUSTRIAL", "UTILITY"),
        ("Petróleo e Gás", "INDUSTRIAL", None),
    ],
)
def test_special_sectors(sector, template, expected):
    assert special_sector(sector, template) == expected


# --- ingestion + on-demand analysis -------------------------------------------------------------


class FakeMarket:
    name = "fake"

    def daily_bars(self, tickers, start, end):
        out = {}
        for t in tickers:
            close = {"CMIG4": D("12"), "CMIG3": D("13")}.get(t)
            if close:
                out[t] = [DailyBar(date(2026, 10, d), close, close, D(10_000_000)) for d in (6, 7, 8)]
        return out

    def index_closes(self, symbol, start, end):
        return []


class FakeEvents:
    def supplement(self, issuer):
        return json.loads((B3 / f"{issuer}_supplement.json").read_text("utf-8"))


def test_ingest_and_analyze_cemig(session_factory):
    with session_factory() as session:
        result = service.ingest(session, today=date(2026, 10, 8), download=False, raw=RAW)
        assert result.errors == []
        assert result.companies == 3
        f = service.fundamentals_for(session, "cmig4", FakeMarket(), FakeEvents(), today=date(2026, 10, 8))
    assert (f.ticker, f.template, f.result.special_sector) == ("CMIG4", "INDUSTRIAL", "UTILITY")
    assert f.shares.source == "B3"
    assert f.price == D("12")
    r = f.result
    assert (r.last_dfp, r.last_itr) == (date(2025, 12, 31), date(2026, 6, 30))
    assert r.profitable_years == 5
    # Market cap = ON ex-treasury × CMIG3 + PN ex-treasury × CMIG4
    assert r.value("market_cap") == (D("956601911") * 13) + (D("1905179984") - D("1100000")) * 12
    assert r.value("daily_liquidity") == D("120000000")
    assert r.value("pe") is not None and r.value("pe") > 0


def test_unknown_ticker(session_factory):
    with session_factory() as session, pytest.raises(service.UnknownTickerError):
        service.fundamentals_for(session, "HGLG11", None, None)
