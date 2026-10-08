"""Daily portfolio valuation and time-weighted return (método de cotas).

Pure: receives the ledger and raw daily closes, returns one point per calendar day. Days without a
quote (weekends, holidays) carry the last close forward.

Daily return with inflows at the start of the day and outflows at the end of it:
    r_d = (V_d + D_d + O_d) / (V_{d-1} + I_d) − 1
V = market value at the close, I = money put in (buys incl. costs), O = money taken out (sales and
fraction auctions, net of costs), D = provents received (net). Provents count as return, buys/sells
do not, so the quota (cota) isolates performance from contributions.
"""

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.portfolio.engine import LedgerEntry, PortfolioResult, apply_entry, sort_entries
from app.portfolio.types import PROVENT_TYPES, TransactionType

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True)
class DailyPoint:
    date: date
    invested: Decimal  # cost of the open positions (valor aplicado)
    market_value: Decimal
    inflow: Decimal
    outflow: Decimal
    provents: Decimal
    quota: Decimal  # cumulative TWR index, starts at 1
    # Tickers valued at cost because no quote was available yet
    missing_prices: tuple[str, ...] = ()


class PriceBook:
    """Last-known-close lookup over raw daily closes."""

    def __init__(self, closes: Mapping[str, Mapping[date, Decimal]]):
        self._dates = {t: sorted(series) for t, series in closes.items()}
        self._closes = closes

    def close_on(self, ticker: str, day: date) -> Decimal | None:
        dates = self._dates.get(ticker)
        if not dates:
            return None
        idx = bisect_right(dates, day) - 1
        return self._closes[ticker][dates[idx]] if idx >= 0 else None


def _flows(entry: LedgerEntry) -> tuple[Decimal, Decimal]:
    price = entry.price or ZERO
    if entry.type == TransactionType.BUY:
        return entry.quantity * price + entry.costs, ZERO
    if entry.type in (TransactionType.SELL, TransactionType.FRACTION_AUCTION):
        return ZERO, entry.quantity * price - entry.costs
    return ZERO, ZERO


def daily_series(entries: Iterable[LedgerEntry], prices: PriceBook, until: date) -> list[DailyPoint]:
    """One point per calendar day from the first entry until `until` (inclusive)."""
    ordered = sort_entries(entries)
    if not ordered:
        return []
    provents_by_day: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for e in ordered:
        if e.type in PROVENT_TYPES and e.is_received:
            provents_by_day[e.payment_date or e.date] += e.provent_net

    result = PortfolioResult()
    points: list[DailyPoint] = []
    quota, prev_value = ONE, ZERO
    idx, day = 0, ordered[0].date
    while day <= until:
        inflow = outflow = ZERO
        while idx < len(ordered) and ordered[idx].date <= day:
            entry = ordered[idx]
            apply_entry(result, entry)
            if entry.date == day:
                i, o = _flows(entry)
                inflow, outflow = inflow + i, outflow + o
            idx += 1

        value, invested, missing = ZERO, ZERO, []
        for pos in result.positions.values():
            if not pos.is_open:
                continue
            invested += pos.total_cost
            close = prices.close_on(pos.ticker, day)
            if close is None:
                missing.append(pos.ticker)
                value += pos.total_cost
            else:
                value += pos.quantity * close
        provents = provents_by_day.get(day, ZERO)
        base = prev_value + inflow
        if base > 0:
            quota *= (value + provents + outflow) / base
        points.append(
            DailyPoint(day, invested, value, inflow, outflow, provents, quota, tuple(sorted(missing)))
        )
        prev_value = value
        day += timedelta(days=1)
    return points


def period_return(points: list[DailyPoint], since: date) -> Decimal | None:
    """TWR between the close of the day before `since` and the last point."""
    if not points:
        return None
    before = [p for p in points if p.date < since]
    base = before[-1].quota if before else ONE
    return points[-1].quota / base - ONE


def cdi_index(daily_rates: Iterable[tuple[date, Decimal]]) -> dict[date, Decimal]:
    """Cumulative CDI index (starts at 1 before the first rate) from daily % rates."""
    index, out = ONE, {}
    for day, rate in sorted(daily_rates):
        index *= ONE + rate / 100
        out[day] = index
    return out
