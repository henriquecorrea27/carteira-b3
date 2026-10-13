"""Fundamental indicators (CLAUDE.md §4.2). Pure: receives the extracted periods, share counts and
market data, returns every indicator with value, unit and a note when it could not be computed.

TTM = latest ITR year-to-date + latest DFP − same year-to-date of the previous year (= sum of the last
four quarters, 4th quarter = DFP − 9-month ITR). Without a newer ITR, the DFP itself is the TTM."""

import math
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
EARNINGS_DROP = Decimal("0.75")  # earnings below 75% of the previous year's count as a drop


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
    operating_cash_flow: Decimal | None
    capex: Decimal | None
    total_assets: Decimal | None
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
    # No value for an ECONOMIC reason (LPA ≤ 0, EBIT ≤ 0, final value ≤ 0, no profitable year), not for lack
    # of data. Rules with `if_invalid: zero` score it as 0 instead of leaving it out (CLAUDE.md §5).
    invalid: bool = False


@dataclass
class FundamentalsResult:
    special_sector: str | None  # FINANCIAL | UTILITY | CYCLICAL | None (general), see app.rules.engine
    indicators: dict[str, Indicator]
    profitable_years: int  # E1: years with positive net income among the last 5 DFPs
    years_available: int
    last_dfp: date | None
    last_itr: date | None
    received_on: date | None
    notes: list[str] = field(default_factory=list)
    template: str | None = None  # INDUSTRIAL | BANK (CVM chart of accounts)
    issuer: str | None = None  # ticker root (PETR), for manual overrides in the rules
    issuer_status: str | None = None  # CVM SIT_EMISSOR (rule E5)
    as_of: date | None = None  # analysis date (staleness of the statements)
    # Inputs of the Graham and Bazin prices, shown step by step in the UI
    net_income_ttm: Decimal | None = None  # attributable to the controlling shareholders
    equity_now: Decimal | None = None  # controlling shareholders' equity, latest balance
    shares_outstanding: Decimal | None = None  # excluding treasury shares
    # Dividends + JCP paid per year / current shares
    dps_by_year: list[tuple[int, Decimal]] = field(default_factory=list)

    def value(self, key: str) -> Decimal | None:
        return self.indicators[key].value


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
    special_sector: str | None = None,
    template: str | None = None,
    *,
    issuer: str | None = None,
    issuer_status: str | None = None,
    b3_pays_dividends: bool | None = None,
    as_of: date | None = None,
) -> FundamentalsResult:
    book = _Book(periods)
    notes: list[str] = []
    out: dict[str, Indicator] = {}

    def add(key, label, value, unit, note=None, invalid=False):
        out[key] = Indicator(key, label, value, unit, note, invalid)

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

    def cagr(key: str, label: str, metric: str) -> None:
        """Base ≤ 0 → N/A (no meaningful rate); final value ≤ 0 with a positive base → invalid (it shrank)."""
        if len(years) < 6:
            return add(key, label, None, "pct", "menos de 6 DFPs")
        base, final = getattr(years[0], metric), getattr(years[-1], metric)
        if base is None or final is None:
            return add(key, label, None, "pct", "dado indisponível")
        if base <= 0:
            return add(key, label, None, "pct", "base ≤ 0")
        if final <= 0:
            return add(key, label, None, "pct", "valor final ≤ 0", invalid=True)
        return add(key, label, Decimal(math.pow(float(final / base), 1 / 5)) - ONE, "pct")

    cagr("cagr_earnings_5y", "CAGR lucro 5a", "net_income_controlling")
    cagr("cagr_revenue_5y", "CAGR receita 5a", "revenue")
    cagr("cagr_book_5y", "CAGR patrimônio 5a", "equity_controlling")

    # Earnings drops: years whose net income fell more than 25% (or turned into a loss) vs. the year before
    drops = None
    if len(years) == 6 and all(y.net_income_controlling is not None for y in years):
        drops = sum(
            1
            for before, y in zip(years, years[1:], strict=False)
            if before.net_income_controlling > 0
            and y.net_income_controlling < before.net_income_controlling * EARNINGS_DROP
        )
    add(
        "earnings_drops_5y",
        "Quedas de lucro > 25% (5a)",
        None if drops is None else Decimal(drops),
        "count",
        None if drops is not None else "menos de 6 DFPs",
    )

    with_dividends = [
        y for y in last5 if y.dividends_paid is not None and y.net_income_controlling is not None
    ]
    payouts = [
        y.dividends_paid / y.net_income_controlling for y in with_dividends if y.net_income_controlling > 0
    ]
    if payouts:
        add(
            "payout_5y",
            "Payout médio 5a",
            _mean(payouts),
            "pct",
            "dividendos e JCP pagos (fluxo de caixa) / lucro",
        )
    elif with_dividends:
        add("payout_5y", "Payout médio 5a", None, "pct", "sem anos com lucro", invalid=True)
    else:
        add("payout_5y", "Payout médio 5a", None, "pct", "dados indisponíveis")

    # Earnings quality: operating cash flow / net income, summed over the last 5 years (both consolidated)
    pairs = [
        (y.operating_cash_flow, y.net_income if y.net_income is not None else y.net_income_controlling)
        for y in last5
        if y.operating_cash_flow is not None
    ]
    pairs = [(fco, ni) for fco, ni in pairs if ni is not None]
    if len(pairs) < 3:
        add("cash_conversion_5y", "FCO / lucro 5a", None, "x", "fluxo de caixa operacional indisponível")
    elif sum(ni for _, ni in pairs) <= 0:
        add("cash_conversion_5y", "FCO / lucro 5a", None, "x", "lucro acumulado ≤ 0", invalid=True)
    else:
        conversion = sum(fco for fco, _ in pairs) / sum(ni for _, ni in pairs)
        add(
            "cash_conversion_5y",
            "FCO / lucro 5a",
            conversion,
            "x",
            None if len(pairs) >= 5 else f"{len(pairs)} anos",
        )

    # Balance sheet
    net_debt = None
    if bal and bal.gross_debt is not None and bal.cash is not None:
        net_debt = bal.gross_debt - bal.cash
    ebitda = ebit_ttm + da_ttm if ebit_ttm is not None and da_ttm is not None else None
    if net_debt is None:
        add("net_debt_ebitda", "Dívida líquida / EBITDA", None, "x", "dívida ou caixa indisponível")
    elif ebitda is None:
        add("net_debt_ebitda", "Dívida líquida / EBITDA", None, "x", "D&A não localizada no fluxo de caixa")
    elif ebitda <= 0:
        add("net_debt_ebitda", "Dívida líquida / EBITDA", None, "x", "EBITDA negativo", invalid=True)
    else:
        add("net_debt_ebitda", "Dívida líquida / EBITDA", net_debt / ebitda, "x")
    add(
        "current_ratio",
        "Liquidez corrente",
        _div(bal.current_assets, bal.current_liabilities) if bal else None,
        "x",
    )
    add("equity_to_assets", "PL / ativo total", _div(bal.equity, bal.total_assets) if bal else None, "pct")

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
    if lpa is not None and lpa <= 0:
        add("pe", "P/L", None, "x", "LPA ≤ 0", invalid=True)
    else:
        add("pe", "P/L", _div(price, lpa), "x")
    add("pb", "P/VP", _div(price, vpa) if vpa and vpa > 0 else None, "x")

    market_cap = None
    if shares and class_prices:
        on_price = class_prices.get("ON") or class_prices.get("PN")
        pn_price = class_prices.get("PN") or class_prices.get("ON")
        market_cap = (shares.on - shares.treasury_on) * on_price + (shares.pn - shares.treasury_pn) * pn_price
        if "ON" not in class_prices and shares.on > 0 or "PN" not in class_prices and shares.pn > 0:
            notes.append("uma das classes sem cotação: usado o preço da outra classe no valor de mercado")
    add("market_cap", "Valor de mercado", market_cap, "brl")

    # EV = market cap + net debt + minority interests (the EBIT is consolidated, so the EV must be too)
    ev = None
    if market_cap is not None and net_debt is not None:
        minority = ZERO
        if bal.equity is not None and bal.equity_controlling is not None:
            minority = bal.equity - bal.equity_controlling
        ev = market_cap + net_debt + minority
    if ev is not None and ebit_ttm is not None and ebit_ttm <= 0:
        add("ev_ebit", "EV/EBIT", None, "x", "EBIT ≤ 0", invalid=True)
    else:
        add("ev_ebit", "EV/EBIT", _div(ev, ebit_ttm), "x")

    # Free cash flow yield: (operating cash flow − capex) TTM / market cap
    fco_ttm, _ = book.ttm("operating_cash_flow")
    capex_ttm, _ = book.ttm("capex")
    fcf = fco_ttm - (capex_ttm or ZERO) if fco_ttm is not None else None
    add(
        "fcf_yield",
        "FCF yield",
        _div(fcf, market_cap) if market_cap and market_cap > 0 else None,
        "pct",
        None if fcf is not None else "fluxo de caixa operacional indisponível",
    )

    # Normalized multiples (cyclicals): 5-year average earnings, EBIT and EBITDA instead of the TTM
    enough = len(last5) >= 3
    avg_ni = _mean([y.net_income_controlling for y in last5 if y.net_income_controlling is not None])
    avg_ebit = _mean([y.ebit for y in last5 if y.ebit is not None])
    avg_ebitda = _mean([y.ebit + y.d_and_a for y in last5 if y.ebit is not None and y.d_and_a is not None])
    lpa_norm = _div(avg_ni, outstanding) if enough else None
    if lpa_norm is not None and lpa_norm <= 0:
        add("pe_norm", "P/L (lucro médio 5a)", None, "x", "lucro médio de 5 anos ≤ 0", invalid=True)
    else:
        add(
            "pe_norm",
            "P/L (lucro médio 5a)",
            _div(price, lpa_norm),
            "x",
            None if enough else "menos de 3 DFPs",
        )
    if enough and ev is not None and avg_ebit is not None and avg_ebit <= 0:
        add("ev_ebit_norm", "EV/EBIT (EBIT médio 5a)", None, "x", "EBIT médio de 5 anos ≤ 0", invalid=True)
    else:
        add("ev_ebit_norm", "EV/EBIT (EBIT médio 5a)", _div(ev, avg_ebit) if enough else None, "x")
    label = "Dívida líquida / EBITDA médio 5a"
    if not enough or net_debt is None or avg_ebitda is None:
        add("net_debt_ebitda_norm", label, None, "x", "dados indisponíveis")
    elif avg_ebitda <= 0:
        add("net_debt_ebitda_norm", label, None, "x", "EBITDA médio negativo", invalid=True)
    else:
        add("net_debt_ebitda_norm", label, net_debt / avg_ebitda, "x")

    graham = None
    if lpa and vpa and lpa > 0 and vpa > 0:
        graham = Decimal(math.sqrt(float(GRAHAM * lpa * vpa)))
    add("graham_price", "Preço justo Graham", graham, "brl", None if graham else "LPA ou VPA ≤ 0")
    add(
        "graham_margin",
        "Margem de segurança Graham",
        _div(graham - price, price) if graham and price else None,
        "pct",
        None if graham else "LPA ou VPA ≤ 0",
    )

    dps_by_year = [
        (y.period_end.year, y.dividends_paid / outstanding)
        for y in last5
        if y.dividends_paid is not None and outstanding
    ]
    dps = [v for _, v in dps_by_year]
    avg_dps = _mean(dps)
    dps_note = "dividendos e JCP pagos (fluxo de caixa CVM) ÷ ações atuais" if dps else None
    if avg_dps == 0 and b3_pays_dividends:
        # Nothing in the CVM cash flows, but the B3 lists recent payments: an account we do not recognize
        avg_dps, dps_note = None, "a CVM não mostra proventos pagos, mas a B3 sim: conferir"
        notes.append(
            "DY sem dados: proventos não localizados no fluxo de caixa da CVM, mas a B3 mostra pagamentos"
        )
    add("dps_5y", "Proventos por ação médios 5a", avg_dps, "brl", dps_note)
    add("dy_5y", "DY médio 5a", _div(avg_dps, price), "pct", dps_note if avg_dps is None and dps else None)
    add("bazin_price", "Preço teto Bazin", avg_dps / BAZIN_YIELD if avg_dps is not None else None, "brl")
    add("daily_liquidity", "Liquidez média diária (2 meses)", daily_liquidity, "brl")

    profitable = sum(
        1 for y in last5 if y.net_income_controlling is not None and y.net_income_controlling > 0
    )
    return FundamentalsResult(
        special_sector=special_sector,
        indicators=out,
        profitable_years=profitable,
        years_available=len(last5),
        last_dfp=book.last_annual.period_end if book.last_annual else None,
        last_itr=book.last_quarter.period_end if book.last_quarter else None,
        received_on=(book.last_quarter or book.last_annual).received_on if bal else None,
        notes=notes,
        template=template,
        issuer=issuer,
        issuer_status=issuer_status,
        as_of=as_of,
        net_income_ttm=ni_ttm,
        equity_now=eq_now,
        shares_outstanding=outstanding,
        dps_by_year=dps_by_year,
    )
