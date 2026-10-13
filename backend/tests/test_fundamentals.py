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
from app.fundamentals.indicators import compute
from app.fundamentals.shares import ShareCount, from_b3, from_cvm
from app.market_data.base import DailyBar
from app.rules.engine import classify_sector

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


def test_cash_flow_operations_and_capex():
    (p,) = periods_of(CEMIG, "dfp_cia_aberta_2025.zip", "DFP")
    f = p.figures
    assert f.operating_cash_flow == D("4076534000")  # 6.01 Caixa Líquido Atividades Operacionais
    # Capex = No Imobilizado 699.182 + No Intangível 378.608 + Em ativos de contrato 5.386.242 (thousands);
    # "Alienação de ativos imobilizados e intangíveis" (an inflow) is not capex
    assert f.capex == D("6464032000")
    assert f.dividends_paid == D("3966145000")
    assert f.total_assets == D("67028076000")


def test_dividend_lines_with_other_names():
    from app.fundamentals.extract import Account, Statement, dividends_paid

    def dfc(*lines):
        return Statement([Account(f"6.03.0{i}", text, D(v)) for i, (text, v) in enumerate(lines, 1)])

    assert dividends_paid(dfc(("Pagamento de Proventos", "-1444745"))) == D("1444745")  # B3
    assert dividends_paid(dfc(("Juros s/ o capital próprio", "-630809"))) == D("630809")  # ABC Brasil
    assert dividends_paid(dfc(("Pagamento e remuneração aos acionistas", "-12186149"))) == D(
        "12186149"
    )  # Axia
    assert dividends_paid(dfc(("Dividendos pagos a acionistas não controladores", "-10"))) == D(0)


def test_zero_attribution_line_means_all_controlling():
    from app.fundamentals.extract import Account, Statement, extract

    # Banco ABC 2022: "Atribuído a Sócios da Empresa Controladora" filed as 0 under a profit of 789.718
    dre = Statement([
        Account("3.11", "Lucro ou Prejuízo Líquido do Período", D("789718")),
        Account("3.11.01", "Atribuído a Sócios da Empresa Controladora", D(0)),
        Account("3.11.02", "Atribuído a Sócios Não Controladores", D(0)),
    ])  # fmt: skip
    assert extract(Statement([]), Statement([]), dre, None).net_income_controlling == D("789718")


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
    operating_cash_flow: D | None = None
    capex: D | None = None
    total_assets: D | None = None


def annual(year, ni, rev, eq, div, ebit=None, da=None):
    return P("DFP", date(year, 12, 31), date(year, 1, 1), revenue=D(rev), net_income_controlling=D(ni),
             equity=D(eq), equity_controlling=D(eq), dividends_paid=D(div), ebit=D(ebit or ni), d_and_a=D(da or 0),
             current_assets=D(300), current_liabilities=D(200), cash=D(100), gross_debt=D(400),
             operating_cash_flow=D(ni), capex=D(20), total_assets=D(eq) * 4)  # fmt: skip


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
           cash=D(150), gross_debt=D(450), operating_cash_flow=D(130), capex=D(40), total_assets=D(6400))  # fmt: skip
    q2_prior = P("ITR", date(2025, 6, 30), date(2025, 1, 1), comparative=True, net_income_controlling=D(90),
                 ebit=D(140), d_and_a=D(45), revenue=D(700), operating_cash_flow=D(100), capex=D(30))  # fmt: skip
    q2_prior_balance = P("ITR", date(2025, 6, 30), date(2025, 1, 1), net_income_controlling=D(90), ebit=D(140),
                         d_and_a=D(45), revenue=D(700), equity=D(1400), equity_controlling=D(1400),
                         operating_cash_flow=D(100), capex=D(30))  # fmt: skip
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
    # Inputs shown step by step in the UI: LPA = 230 / 100, VPA = 1600 / 100, DPS per year = paid / 100
    assert (r.net_income_ttm, r.equity_now, r.shares_outstanding) == (D(230), D(1600), D(100))
    assert r.dps_by_year == [
        (2021, D("0.6")),
        (2022, D("0.7")),
        (2023, D("0.8")),
        (2024, D("0.9")),
        (2025, D("1")),
    ]


def test_negative_eps_makes_pe_invalid_not_missing():
    data = company()
    data[-3].net_income_controlling = D(-500)  # loss in 2026 YTD
    r = compute(
        data, ShareCount(D(100), D(0), D(0), D(0), "B3", None), D(23), {"ON": D(23)}, None, None, None
    )
    pe = r.indicators["pe"]
    assert (pe.value, pe.note, pe.invalid) == (None, "LPA ≤ 0", True)
    assert r.value("graham_price") is None


def test_cash_flow_indicators():
    r = run()
    # FCO = net income every year → conversion 1,0 ; FCF TTM = (130 + 200 − 100) − (40 + 20 − 30) = 200
    assert r.value("cash_conversion_5y") == D(1)
    assert r.value("fcf_yield") == D(200) / D(2300)
    assert r.value("equity_to_assets") == D("0.25")
    assert r.value("cagr_book_5y").quantize(D("0.0001")) == D("0.0845")  # (1500/1000)^(1/5) − 1
    assert r.value("earnings_drops_5y") == 0


def test_earnings_drops_and_invalid_cagr():
    data = company()
    data[2].net_income_controlling = D(100)  # 2022: 120 → 100, −17% (not a drop)
    data[3].net_income_controlling = D(70)  # 2023: 100 → 70, −30% (drop)
    data[5].net_income_controlling = D(-10)  # 2025: loss (drop)
    r = compute(data, None, None, {}, None)
    assert r.value("earnings_drops_5y") == 2
    cagr = r.indicators["cagr_earnings_5y"]
    assert (cagr.value, cagr.invalid, cagr.note) == (None, True, "valor final ≤ 0")
    data[0].net_income_controlling = D(-5)  # base ≤ 0 → no rate at all (N/A, not invalid)
    cagr = compute(data, None, None, {}, None).indicators["cagr_earnings_5y"]
    assert (cagr.value, cagr.invalid) == (None, False)


def test_ev_includes_minority_interests_and_normalized_multiples():
    data = company()
    data[-3].equity = D(1700)  # 100 of minority interests in the latest balance
    r = compute(data, ShareCount(D(100), D(0), D(0), D(0), "B3", None), D(23), {"ON": D(23)}, None)
    ev = D(2300) + D(300) + D(100)
    assert r.value("ev_ebit") == ev / D(330)
    # 5-year averages (2021–2025): net income 160, EBIT (120+140+160+180+300)/5 = 180, EBITDA 180 + 20
    assert r.value("pe_norm") == D(23) / D("1.6")
    assert r.value("ev_ebit_norm") == ev / D(180)
    assert r.value("net_debt_ebitda_norm") == D(300) / D(200)


def test_dy_is_missing_when_cvm_shows_no_dividends_but_b3_does():
    data = company()
    for p in data:
        p.dividends_paid = D(0)
    shares = ShareCount(D(100), D(0), D(0), D(0), "B3", None)
    r = compute(data, shares, D(23), {"ON": D(23)}, None, b3_pays_dividends=True)
    assert r.value("dy_5y") is None
    assert "B3" in r.indicators["dy_5y"].note
    assert any("DY sem dados" in n for n in r.notes)
    assert compute(data, shares, D(23), {"ON": D(23)}, None, b3_pays_dividends=False).value("dy_5y") == 0


@pytest.mark.parametrize(
    ("sector", "template", "ticker", "expected"),
    [
        ("Bancos", "BANK", None, "FINANCIAL"),
        ("Emp. Adm. Part. - Seguradoras e Corretoras", "INDUSTRIAL", None, "FINANCIAL"),
        ("Emp. Adm. Part. - Intermediação Financeira", "INDUSTRIAL", None, "FINANCIAL"),
        ("Emp. Adm. Part. - Crédito Imobiliário", "INDUSTRIAL", None, "FINANCIAL"),
        ("Energia Elétrica", "INDUSTRIAL", None, "UTILITY"),
        ("Saneamento, Serv. Água e Gás", "INDUSTRIAL", None, "UTILITY"),
        ("Saneamento, Serv. Água e Gás", "INDUSTRIAL", "AMBP3", None),  # manual override
        ("Petróleo e Gás", "INDUSTRIAL", None, "CYCLICAL"),
        ("Emp. Adm. Part. - Metalurgia e Siderurgia", "INDUSTRIAL", None, "CYCLICAL"),
        ("Agricultura (Açúcar, Álcool e Cana)", "INDUSTRIAL", None, "CYCLICAL"),
        ("Bolsas de Valores/Mercadorias e Futuros", "INDUSTRIAL", None, None),
        ("Alimentos", "INDUSTRIAL", None, None),
    ],
)
def test_special_sectors(sector, template, ticker, expected):
    assert classify_sector(sector, template, ticker) == expected


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
    assert (f.result.issuer, f.result.issuer_status) == ("CMIG", "FASE OPERACIONAL")
    assert f.result.as_of == date(2026, 10, 8)
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
