"""Read models for the dashboard: positions with market data, summary with TWR vs benchmarks,
patrimony history, allocation and provents. Everything is recomputed from the ledger + cached prices."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import cached_property

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_data import service as market
from app.models import Asset, Transaction
from app.portfolio.engine import LedgerEntry, PortfolioResult, build_portfolio
from app.portfolio.performance import DailyPoint, PriceBook, cdi_index, daily_series, period_return
from app.portfolio.tickers import infer_asset_class
from app.portfolio.types import PROVENT_TYPES, AssetClass, ProventStatus

ZERO, ONE = Decimal(0), Decimal(1)
RANGES = {"1m": 31, "6m": 183, "12m": 365, "5y": 365 * 5}
CLASS_LABELS = {
    AssetClass.STOCK: "Ações",
    AssetClass.FII: "FIIs",
    AssetClass.ETF: "ETFs",
    AssetClass.BDR: "BDRs",
}


def _ratio(num: Decimal, den: Decimal) -> Decimal | None:
    return num / den if den else None


class DashboardContext:
    """Loads the ledger and market data once per request."""

    def __init__(self, session: Session, today: date | None = None):
        self.session = session
        self.today = today or date.today()
        self.rows = list(session.scalars(select(Transaction)))
        self.entries: list[LedgerEntry] = [row.to_entry() for row in self.rows]
        self.assets = {a.ticker: a for a in session.scalars(select(Asset))}
        self.quotes = market.latest_quotes(session)

    @cached_property
    def portfolio(self) -> PortfolioResult:
        return build_portfolio(self.entries)

    @cached_property
    def prices(self) -> PriceBook:
        return market.load_price_book(self.session)

    @cached_property
    def series(self) -> list[DailyPoint]:
        return daily_series(self.entries, self.prices, until=self.today)

    @cached_property
    def provent_rows(self) -> list[Transaction]:
        return [r for r in self.rows if r.type in PROVENT_TYPES]

    def provents_12m_by_ticker(self) -> dict[str, Decimal]:
        start = self.today - timedelta(days=365)
        out: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for r in self.provent_rows:
            if (
                r.status != ProventStatus.ANNOUNCED
                and r.payment_date
                and start < r.payment_date <= self.today
            ):
                out[r.ticker] += r.net_amount or ZERO
        return out

    def asset_class(self, ticker: str) -> AssetClass:
        asset = self.assets.get(ticker)
        return AssetClass(asset.asset_class) if asset else infer_asset_class(ticker)

    def sector(self, ticker: str) -> str | None:
        asset = self.assets.get(ticker)
        return (asset.sector_override or asset.sector) if asset else None


@dataclass
class PositionView:
    ticker: str
    name: str | None
    asset_class: AssetClass
    sector: str | None
    quantity: Decimal
    avg_price: Decimal
    total_cost: Decimal
    realized_result: Decimal
    provents_net: Decimal
    provents_net_12m: Decimal
    provents_receivable_net: Decimal
    pending_bonus_cost: bool
    first_date: date | None
    current_price: Decimal | None
    price_date: date | None
    day_change_pct: Decimal | None
    market_value: Decimal | None
    open_result: Decimal | None
    open_result_pct: Decimal | None
    weight_pct: Decimal | None
    yield_on_cost_pct: Decimal | None
    rules: dict | None = None  # latest analysis snapshot (stocks only)


def positions(ctx: DashboardContext, include_closed: bool = False) -> list[PositionView]:
    prov_12m = ctx.provents_12m_by_ticker()
    views = []
    for pos in ctx.portfolio.positions.values():
        if not include_closed and not pos.is_open:
            continue
        quote = ctx.quotes.get(pos.ticker)
        value = pos.quantity * quote.close if quote and pos.is_open else None
        asset = ctx.assets.get(pos.ticker)
        views.append(
            PositionView(
                ticker=pos.ticker,
                name=asset.name if asset else None,
                asset_class=ctx.asset_class(pos.ticker),
                sector=ctx.sector(pos.ticker),
                quantity=pos.quantity,
                avg_price=pos.avg_price,
                total_cost=pos.total_cost,
                realized_result=pos.realized_result,
                provents_net=pos.provents_net,
                provents_net_12m=prov_12m.get(pos.ticker, ZERO),
                provents_receivable_net=pos.provents_receivable_net,
                pending_bonus_cost=pos.pending_bonus_cost,
                first_date=pos.first_date,
                current_price=quote.close if quote else None,
                price_date=quote.date if quote else None,
                day_change_pct=_ratio(quote.close, quote.previous_close) - ONE
                if quote and quote.previous_close
                else None,
                market_value=value,
                open_result=value - pos.total_cost if value is not None else None,
                open_result_pct=_ratio(value - pos.total_cost, pos.total_cost) if value is not None else None,
                weight_pct=None,
                yield_on_cost_pct=_ratio(prov_12m.get(pos.ticker, ZERO), pos.total_cost)
                if pos.is_open
                else None,
            )
        )
    snapshots = _latest_rules(ctx.session, [v.ticker for v in views])
    for v in views:
        v.rules = snapshots.get(v.ticker)
    total_value = sum((v.market_value or v.total_cost for v in views if v.quantity > 0), ZERO)
    for v in views:
        if v.quantity > 0 and total_value:
            v.weight_pct = (v.market_value or v.total_cost) / total_value
    return sorted(views, key=lambda v: v.market_value or v.total_cost, reverse=True)


def _latest_rules(session: Session, tickers: list[str]) -> dict[str, dict]:
    from app.rules.service import latest_snapshots  # local import: rules depends on portfolio modules

    return {
        t: {
            "decision": s.decision,
            "score_final": float(s.score_final) if s.score_final is not None else None,
            "score_quality": float(s.score_quality) if s.score_quality is not None else None,
            "score_price": float(s.score_price) if s.score_price is not None else None,
            "inconclusive": s.inconclusive,
            "main_reason": s.main_reason,
            "date": s.date,
        }
        for t, s in latest_snapshots(session, tickers).items()
    }


@dataclass
class SummaryView:
    invested: Decimal
    market_value: Decimal
    open_result: Decimal
    open_result_pct: Decimal | None
    realized_result: Decimal
    provents_net_total: Decimal
    provents_net_12m: Decimal
    provents_receivable: Decimal
    total_result: Decimal  # open + realized + provents
    return_total: Decimal | None  # TWR since the first trade
    return_12m: Decimal | None
    ibov_12m: Decimal | None
    cdi_12m: Decimal | None
    day_change: Decimal | None
    open_positions: int
    pending_bonus_cost: int
    prices_as_of: date | None
    missing_prices: list[str]


def _benchmark_return(
    index: dict[date, Decimal], since: date, until: date, base_if_missing: Decimal | None = None
) -> Decimal | None:
    """Return of a cumulative index between the last value before `since` and the last up to `until`.
    When the history starts after `since`, `base_if_missing` is used as the base (1 for the CDI index,
    which is built starting at 1); without it the first available value is used."""
    days = sorted(d for d in index if d <= until)
    if not days:
        return None
    before = [d for d in days if d < since]
    if before:
        return index[days[-1]] / index[before[-1]] - ONE
    base = base_if_missing if base_if_missing is not None else index[days[0]]
    return index[days[-1]] / base - ONE


def benchmark_indexes(ctx: DashboardContext) -> dict[str, dict[date, Decimal]]:
    return {
        "ibov": dict(market.benchmark_series(ctx.session, market.IBOV)),
        "cdi": cdi_index(market.benchmark_series(ctx.session, market.CDI)),
    }


def summary(ctx: DashboardContext) -> SummaryView:
    views = positions(ctx)
    open_views = [v for v in views if v.quantity > 0]
    series = ctx.series
    last = series[-1] if series else None
    # Same window for portfolio and benchmarks: 12 months, or since the first trade if more recent
    year_ago = ctx.today - timedelta(days=364)
    if series:
        year_ago = max(year_ago, series[0].date)
    bench = benchmark_indexes(ctx)
    invested = sum((v.total_cost for v in open_views), ZERO)
    market_value = last.market_value if last else ZERO
    realized = sum((p.realized_result for p in ctx.portfolio.positions.values()), ZERO)
    prov_total = sum((p.provents_net for p in ctx.portfolio.positions.values()), ZERO)
    day_change = None
    if len(series) >= 2 and series[-2].market_value:
        prev, cur = series[-2], series[-1]
        day_change = cur.market_value - prev.market_value - cur.inflow + cur.outflow
    price_dates = [v.price_date for v in open_views if v.price_date]
    return SummaryView(
        invested=invested,
        market_value=market_value,
        open_result=market_value - invested,
        open_result_pct=_ratio(market_value - invested, invested),
        realized_result=realized,
        provents_net_total=prov_total,
        provents_net_12m=sum(ctx.provents_12m_by_ticker().values(), ZERO),
        provents_receivable=sum((p.provents_receivable_net for p in ctx.portfolio.positions.values()), ZERO),
        total_result=market_value - invested + realized + prov_total,
        return_total=last.quota - ONE if last else None,
        return_12m=period_return(series, year_ago),
        ibov_12m=_benchmark_return(bench["ibov"], year_ago, ctx.today),
        cdi_12m=_benchmark_return(bench["cdi"], year_ago, ctx.today, base_if_missing=ONE),
        day_change=day_change,
        open_positions=len(open_views),
        pending_bonus_cost=sum(1 for v in open_views if v.pending_bonus_cost),
        prices_as_of=max(price_dates) if price_dates else None,
        missing_prices=list(last.missing_prices) if last else [],
    )


@dataclass
class HistoryPoint:
    date: date
    invested: Decimal
    market_value: Decimal
    portfolio_return: Decimal
    ibov_return: Decimal | None
    cdi_return: Decimal | None


def _value_on(index: dict[date, Decimal], days: list[date], day: date) -> Decimal | None:
    i = bisect_right(days, day) - 1
    return index[days[i]] if i >= 0 else None


def history(ctx: DashboardContext, range_key: str = "12m") -> list[HistoryPoint]:
    series = ctx.series
    if not series:
        return []
    first_day = series[0].date
    start = first_day if range_key == "all" else max(first_day, ctx.today - timedelta(days=RANGES[range_key]))
    if range_key == "ytd":
        start = max(first_day, date(ctx.today.year, 1, 1))
    window = [p for p in series if p.date >= start]
    base_point = next((p for p in reversed(series) if p.date < start), None)
    base_quota = base_point.quota if base_point else ONE
    bench = benchmark_indexes(ctx)
    bench_days = {k: sorted(v) for k, v in bench.items()}
    base_day = start - timedelta(days=1)
    bases = {k: _value_on(bench[k], bench_days[k], base_day) for k in bench}

    # Long ranges are sampled at month ends to keep the payload small
    if (window[-1].date - window[0].date).days > 400:
        window = [
            p for i, p in enumerate(window) if i == len(window) - 1 or (p.date + timedelta(days=1)).day == 1
        ]

    out = []
    for p in window:
        rel = {}
        for key in bench:
            value = _value_on(bench[key], bench_days[key], p.date)
            rel[key] = value / bases[key] - ONE if value is not None and bases[key] else None
        out.append(
            HistoryPoint(
                date=p.date,
                invested=p.invested,
                market_value=p.market_value,
                portfolio_return=p.quota / base_quota - ONE,
                ibov_return=rel["ibov"],
                cdi_return=rel["cdi"],
            )
        )
    return out


@dataclass
class AllocationSlice:
    key: str
    label: str
    value: Decimal
    pct: Decimal


def allocation(ctx: DashboardContext) -> dict[str, list[AllocationSlice]]:
    views = [v for v in positions(ctx) if v.quantity > 0]
    total = sum((v.market_value or v.total_cost for v in views), ZERO)
    groups: dict[str, dict[str, tuple[str, Decimal]]] = {"class": {}, "sector": {}, "asset": {}}
    for v in views:
        value = v.market_value or v.total_cost
        for dim, key, label in (
            ("class", v.asset_class.value, CLASS_LABELS[v.asset_class]),
            ("sector", v.sector or "SEM_SETOR", v.sector or "Sem setor"),
            ("asset", v.ticker, v.ticker),
        ):
            old = groups[dim].get(key, (label, ZERO))
            groups[dim][key] = (label, old[1] + value)
    return {
        dim: sorted(
            (
                AllocationSlice(k, label, value, value / total if total else ZERO)
                for k, (label, value) in g.items()
            ),
            key=lambda s: s.value,
            reverse=True,
        )
        for dim, g in groups.items()
    }
