"""Fundamental indicators (CLAUDE.md §4.2). Pure: receives the extracted periods, share counts and
market data, returns every indicator with value, unit and a note when it could not be computed.

TTM = latest ITR year-to-date + latest DFP − same year-to-date of the previous year (= sum of the last
four quarters, 4th quarter = DFP − 9-month ITR). Without a newer ITR, the DFP itself is the TTM."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.fundamentals.shares import ShareCount

ZERO, ONE = Decimal(0), Decimal(1)
TAX_ROIC = Decimal("0.34")
BAZIN_YIELD = Decimal("0.06")
GRAHAM = Decimal("22.5")

FINANCIAL_SECTORS = (
    r"bancos|seguradoras|intermediacao financeira|arrendamento mercantil|previdencia|capitalizacao"
)
UTILITY_SECTORS = r"energia eletrica|saneamento|agua e gas"


class Period(Protocol):
    doc_type: str
    period_start: date | None
    period_end: date
    comparative: bool
    received_on: date | None
    revenue: Decimal | None
    ebit: Decimal | None
    net_income: Decimal | None
    net_income_controlling: Decimal | None
    d_and_a: Decimal | None
    dividends_paid: Decimal | None
    current_assets: Decimal | None
    current_liabilities: Decimal | None
    cash: Decimal | None
    gross_debt: Decimal | None
    equity: Decimal | None
    equity_controlling: Decimal | None


@dataclass
class Indicator:
    key: str
    label: str
    value: Decimal | None
    unit: str  # pct (fraction) | x | brl | count
    note: str | None = None


@dataclass
class FundamentalsResult:
    special_sector: str | None  # FINANCIAL | UTILITY | None
    indicators: dict[str, Indicator]
    profitable_years: int  # E1: years with positive net income among the last 5 DFPs
    years_available: int
    last_dfp: date | None
    last_itr: date | None
    received_on: date | None
    notes: list[str] = field(default_factory=list)

    def value(self, key: str) -> Decimal | None:
        return self.indicators[key].value


def special_sector(sector: str | None, template: str | None) -> str | None:
    text = (sector or "").lower()
    text = text.translate(str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc"))
    if template == "BANK" or re.search(FINANCIAL_SECTORS, text):
        return "FINANCIAL"
    if re.search(UTILITY_SECTORS, text):
        return "UTILITY"
    return None


def _div(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, ZERO) / len(values) if values else None


def _one_year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29/02
        return day.replace(year=day.year - 1, day=28)


class _Book:
    def __init__(self, periods: Sequence[Period]):
        self.annual = sorted(
            (p for p in periods if p.doc_type == "DFP" and not p.comparative), key=lambda p: p.period_end
        )
        self.itr = {
            p.period_end: p
            for p in sorted(periods, key=lambda p: p.comparative, reverse=True)
            if p.doc_type == "ITR"
        }
        self.last_annual = self.annual[-1] if self.annual else None
        newer = [
            p
            for p in self.itr.values()
            if not p.comparative and (self.last_annual is None or p.period_end > self.last_annual.period_end)
        ]
        self.last_quarter = max(newer, key=lambda p: p.period_end) if newer else None

    @property
    def latest_balance(self) -> Period | None:
        return self.last_quarter or self.last_annual

    def balance_year_before(self) -> Period | None:
        latest = self.latest_balance
        if latest is None:
            return None
        target = _one_year_before(latest.period_end)
        for p in [*self.annual, *self.itr.values()]:
            if p.period_end == target and not p.comparative:
                return p
        return None

    def ttm(self, metric: str) -> tuple[Decimal | None, str | None]:
        annual = self.last_annual
        if annual is None:
            return None, "sem DFP"
        value = getattr(annual, metric)
        q = self.last_quarter
        if q is None:
            return value, None
        prior = self.itr.get(_one_year_before(q.period_end))
        if value is None:
            return None, None  # metric not applicable (e.g. EBIT for banks)
        current, previous = getattr(q, metric), getattr(prior, metric) if prior else None
        if current is None or previous is None:
            return value, "TTM indisponível: usado o último DFP"
        return current + value - previous, None

    def last_years(self, n: int) -> list[Period]:
        return self.annual[-n:]


def compute(
    periods: Sequence[Period],
    shares: ShareCount | None,
    price: Decimal | None,
    class_prices: dict[str, Decimal],
    daily_liquidity: Decimal | None,
    sector: str | None,
    template: str | None,
) -> FundamentalsResult:
    book = _Book(periods)
    notes: list[str] = []
    out: dict[str, Indicator] = {}

    def add(key, label, value, unit, note=None):
        out[key] = Indicator(key, label, value, unit, note)

    ni_ttm, n1 = book.ttm("net_income_controlling")
    ebit_ttm, n2 = book.ttm("ebit")
    da_ttm, _ = book.ttm("d_and_a")
    for n in {n1, n2} - {None}:
        notes.append(n)
    bal = book.latest_balance
    prev_bal = book.balance_year_before()

    # Profitability
    eq_now = bal.equity_controlling if bal else None
    eq_prev = prev_bal.equity_controlling if prev_bal else None
    avg_eq = (eq_now + eq_prev) / 2 if eq_now is not None and eq_prev is not None else eq_now
    add(
        "roe",
        "ROE (TTM)",
        _div(ni_ttm, avg_eq) if avg_eq and avg_eq > 0 else None,
        "pct",
        None if eq_prev is not None else "PL de 12 meses atrás indisponível: usado o PL atual",
    )

    years = book.last_years(6)
    roes = []
    for i, y in enumerate(years):
        if i == 0 and len(years) == 6:
            continue  # base year only feeds the average equity / CAGR
        before = years[i - 1].equity_controlling if i > 0 else None
        eq = y.equity_controlling
        base = (eq + before) / 2 if eq is not None and before is not None else eq
        if base and base > 0 and y.net_income_controlling is not None:
            roes.append(y.net_income_controlling / base)
    last5 = book.last_years(5)
    add(
        "roe_5y",
        "ROE médio 5a",
        _mean(roes) if len(roes) >= 3 else None,
        "pct",
        None
        if len(roes) >= 5
        else f"média de {len(roes)} ano(s)"
        if len(roes) >= 3
        else "menos de 3 anos de DFP",
    )

    margins = [
        y.net_income_controlling / y.revenue
        for y in last5
        if y.revenue and y.revenue > 0 and y.net_income_controlling is not None
    ]
    add(
        "net_margin_5y",
        "Margem líquida média 5a",
        _mean(margins) if len(margins) >= 3 else None,
        "pct",
        None if len(margins) >= 3 else "receita indisponível",
    )

    def cagr(metric: str):
        if len(years) < 6:
            return None, "menos de 6 DFPs"
        base, final = getattr(years[0], metric), getattr(years[-1], metric)
        if base is None or final is None:
            return None, "dado indisponível"
        if base <= 0 or final <= 0:
            return None, "base ou valor final ≤ 0"
        return Decimal(math.pow(float(final / base), 1 / 5)) - ONE, None

    v, n = cagr("net_income_controlling")
    add("cagr_earnings_5y", "CAGR lucro 5a", v, "pct", n)
    v, n = cagr("revenue")
    add("cagr_revenue_5y", "CAGR receita 5a", v, "pct", n)

    payouts = [
        y.dividends_paid / y.net_income_controlling
        for y in last5
        if y.dividends_paid is not None and y.net_income_controlling and y.net_income_controlling > 0
    ]
    add(
        "payout_5y",
        "Payout médio 5a",
        _mean(payouts) if payouts else None,
        "pct",
        "dividendos e JCP pagos (fluxo de caixa) / lucro" if payouts else "sem anos com lucro",
    )

    # Balance sheet
    net_debt = None
    if bal and bal.gross_debt is not None and bal.cash is not None:
        net_debt = bal.gross_debt - bal.cash
    ebitda = ebit_ttm + da_ttm if ebit_ttm is not None and da_ttm is not None else None
    nd_note = None
    nd_ebitda = None
    if net_debt is None:
        nd_note = "dívida ou caixa indisponível"
    elif ebitda is None:
        nd_note = "D&A não localizada no fluxo de caixa"
    elif ebitda <= 0:
        nd_note = "EBITDA negativo"
    else:
        nd_ebitda = net_debt / ebitda
    add("net_debt_ebitda", "Dívida líquida / EBITDA", nd_ebitda, "x", nd_note)
    add(
        "current_ratio",
        "Liquidez corrente",
        _div(bal.current_assets, bal.current_liabilities) if bal else None,
        "x",
    )

    invested = None
    if bal and bal.equity is not None and bal.gross_debt is not None and bal.cash is not None:
        invested = bal.equity + bal.gross_debt - bal.cash
    roic = (
        ebit_ttm * (ONE - TAX_ROIC) / invested if ebit_ttm is not None and invested and invested > 0 else None
    )
    add("roic", "ROIC", roic, "pct")

    # Per share and valuation
    outstanding = shares.outstanding if shares and shares.outstanding > 0 else None
    lpa = _div(ni_ttm, outstanding)
    vpa = _div(eq_now, outstanding)
    add("eps", "LPA (TTM)", lpa, "brl")
    add("bvps", "VPA", vpa, "brl")
    add(
        "pe",
        "P/L",
        _div(price, lpa) if lpa and lpa > 0 else None,
        "x",
        "LPA ≤ 0" if lpa is not None and lpa <= 0 else None,
    )
    add("pb", "P/VP", _div(price, vpa) if vpa and vpa > 0 else None, "x")

    market_cap = None
    if shares and class_prices:
        on_price = class_prices.get("ON") or class_prices.get("PN")
        pn_price = class_prices.get("PN") or class_prices.get("ON")
        market_cap = (shares.on - shares.treasury_on) * on_price + (shares.pn - shares.treasury_pn) * pn_price
        if "ON" not in class_prices and shares.on > 0 or "PN" not in class_prices and shares.pn > 0:
            notes.append("uma das classes sem cotação: usado o preço da outra classe no valor de mercado")
    add("market_cap", "Valor de mercado", market_cap, "brl")
    ev_ebit = None
    if market_cap is not None and net_debt is not None and ebit_ttm and ebit_ttm > 0:
        ev_ebit = (market_cap + net_debt) / ebit_ttm
    add("ev_ebit", "EV/EBIT", ev_ebit, "x")

    graham = None
    if lpa and vpa and lpa > 0 and vpa > 0:
        graham = Decimal(math.sqrt(float(GRAHAM * lpa * vpa)))
    add("graham_price", "Preço justo Graham", graham, "brl", None if graham else "LPA ou VPA ≤ 0")
    add(
        "graham_margin",
        "Margem de segurança Graham",
        _div(graham - price, price) if graham and price else None,
        "pct",
    )

    dps = [y.dividends_paid / outstanding for y in last5 if y.dividends_paid is not None and outstanding]
    avg_dps = _mean(dps)
    add(
        "dps_5y",
        "Proventos por ação médios 5a",
        avg_dps,
        "brl",
        "dividendos e JCP pagos (fluxo de caixa CVM) ÷ ações atuais" if dps else None,
    )
    add("dy_5y", "DY médio 5a", _div(avg_dps, price), "pct")
    add("bazin_price", "Preço teto Bazin", avg_dps / BAZIN_YIELD if avg_dps is not None else None, "brl")
    add("daily_liquidity", "Liquidez média diária (2 meses)", daily_liquidity, "brl")

    profitable = sum(
        1 for y in last5 if y.net_income_controlling is not None and y.net_income_controlling > 0
    )
    return FundamentalsResult(
        special_sector=special_sector(sector, template),
        indicators=out,
        profitable_years=profitable,
        years_available=len(last5),
        last_dfp=book.last_annual.period_end if book.last_annual else None,
        last_itr=book.last_quarter.period_end if book.last_quarter else None,
        received_on=(book.last_quarter or book.last_annual).received_on if bal else None,
        notes=notes,
    )
