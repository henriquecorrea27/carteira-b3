"""Keeps price_history and benchmark_history up to date. External failures are recorded in
data_source_status and never raised to the caller: the app keeps working with the cached data."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.parallel import fetch_all
from app.market_data.base import DailyBar, MarketDataError, MarketDataProvider, RatesProvider
from app.models import BenchmarkHistory, DataSourceStatus, PriceHistory, Transaction
from app.portfolio.engine import LedgerError, build_portfolio
from app.portfolio.performance import PriceBook

log = logging.getLogger(__name__)

IBOV, CDI = "IBOV", "CDI"
IBOV_SYMBOL = "^BVSP"
SOURCE_PRICES, SOURCE_IBOV, SOURCE_CDI = "prices", "ibov", "cdi"
# Fetch a few days before the first trade so the first valuation has a close to fall back on
_LOOKBACK = timedelta(days=7)
# Rows of the last days are fetched again: a row cached during the session holds an intraday price
REVISE = timedelta(days=7)


@dataclass
class RefreshResult:
    prices_inserted: int = 0
    benchmarks_inserted: int = 0
    errors: list[str] = field(default_factory=list)
    tickers_without_data: list[str] = field(default_factory=list)


def record_status(session: Session, source: str, ok: bool, message: str | None = None) -> None:
    now = datetime.now(UTC)
    status = session.get(DataSourceStatus, source) or DataSourceStatus(source=source)
    status.last_attempt_at = now
    status.ok = ok
    status.message = message
    if ok:
        status.last_success_at = now
    session.merge(status)


def tracked_tickers(session: Session) -> dict[str, date]:
    """Every ticker the user holds or held, with its first ledger date."""
    first: dict[str, date] = {}
    rows = session.execute(select(Transaction.ticker, Transaction.target_ticker, Transaction.date))
    for ticker, target, day in rows:
        for t in (ticker, target):
            if t and (t not in first or day < first[t]):
                first[t] = day
    return first


def _ledger_ends(session: Session) -> dict[str, date]:
    """Last ledger date of every ticker (sale, provent, event...)."""
    last: dict[str, date] = {}
    for ticker, target, day in session.execute(
        select(Transaction.ticker, Transaction.target_ticker, Transaction.date)
    ):
        for t in (ticker, target):
            if t and (t not in last or day > last[t]):
                last[t] = day
    return last


def _held(session: Session) -> set[str] | None:
    """Open positions; None when the ledger does not replay (then every ticker is refreshed)."""
    try:
        entries = [t.to_entry() for t in session.scalars(select(Transaction))]
        return {p.ticker for p in build_portfolio(entries).open_positions}
    except LedgerError:
        return None


def _last_dates(session: Session) -> dict[str, date]:
    rows = session.execute(
        select(PriceHistory.ticker, func.max(PriceHistory.date)).group_by(PriceHistory.ticker)
    )
    return dict(rows.all())


BAR_COLUMNS = ("close", "close_adjusted", "volume", "open", "high", "low")


def store_bars(
    session: Session,
    ticker: str,
    bars: list[DailyBar],
    source: str,
    update: tuple[str, ...] = (),
    recent_update: tuple[str, ...] = (),
    recent_from: date | None = None,
) -> None:
    """Writes daily bars with one statement per group (a statement per row made a 6-year sync slow).
    A cached row gets the `update` columns rewritten (nothing when empty); rows on or after `recent_from`
    also the `recent_update` ones."""
    rows = [
        {"ticker": ticker, "date": b.date, "source": source} | {c: getattr(b, c) for c in BAR_COLUMNS}
        for b in bars
    ]
    if recent_from is None:
        groups = [(rows, update)]
    else:
        groups = [
            ([r for r in rows if r["date"] < recent_from], update),
            ([r for r in rows if r["date"] >= recent_from], update + recent_update),
        ]
    for group, columns in groups:
        if not group:
            continue
        stmt = insert(PriceHistory)
        if columns:
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "date"], set_={c: stmt.excluded[c] for c in columns}
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["ticker", "date"])
        session.execute(stmt, group)


def refresh_prices(session: Session, provider: MarketDataProvider, today: date) -> RefreshResult:
    """Open positions are fetched again every time; a closed position only until its history covers the
    day it was closed. The fetches run in parallel, the writes here."""
    result = RefreshResult()
    last = _last_dates(session)
    held, ledger_end = _held(session), _ledger_ends(session)
    starts: dict[str, date] = {}
    for ticker, first_day in sorted(tracked_tickers(session).items()):
        if held is not None and ticker not in held and ticker in last and last[ticker] >= ledger_end[ticker]:
            continue
        starts[ticker] = min(last[ticker], today) - REVISE if ticker in last else first_day - _LOOKBACK
    fetched = fetch_all(lambda t: provider.daily_bars([t], starts[t], today).get(t, []), starts)
    failed: list[str] = []
    for ticker in starts:
        bars = fetched[ticker]
        if isinstance(bars, Exception):
            failed.append(ticker)
            log.warning("prices for %s failed: %s", ticker, bars)
            continue
        if not bars and ticker not in last:
            result.tickers_without_data.append(ticker)
        store_bars(session, ticker, bars, provider.name, update=(*BAR_COLUMNS, "source"))
        result.prices_inserted += sum(1 for b in bars if ticker not in last or b.date > last[ticker])
    if failed:
        result.errors.append(f"preços indisponíveis para: {', '.join(failed)}")
    message = result.errors[-1] if failed else None
    if result.tickers_without_data:
        # Usually delisted tickers (e.g. after a merger); they are valued at cost while held
        note = f"sem cotação na fonte: {', '.join(result.tickers_without_data)}"
        message = f"{message}; {note}" if message else note
    record_status(session, SOURCE_PRICES, not failed, message)
    session.commit()
    return result


def _upsert_benchmark(session: Session, code: str, points: list[tuple[date, Decimal]]) -> int:
    for day, value in points:
        stmt = insert(BenchmarkHistory).values(code=code, date=day, value=value)
        session.execute(
            stmt.on_conflict_do_update(index_elements=["code", "date"], set_={"value": stmt.excluded.value})
        )
    return len(points)


def refresh_benchmarks(
    session: Session, provider: MarketDataProvider, rates: RatesProvider, today: date
) -> RefreshResult:
    result = RefreshResult()
    tracked = tracked_tickers(session)
    if not tracked:
        return result
    first_day = min(tracked.values()) - _LOOKBACK
    for code, source, fetch in (
        (IBOV, SOURCE_IBOV, lambda s: provider.index_closes(IBOV_SYMBOL, s, today)),
        (CDI, SOURCE_CDI, lambda s: rates.cdi_daily(s, today)),
    ):
        last = session.scalar(select(func.max(BenchmarkHistory.date)).where(BenchmarkHistory.code == code))
        start = last + timedelta(days=1) if last else first_day
        if start > today:
            continue
        try:
            result.benchmarks_inserted += _upsert_benchmark(session, code, fetch(start))
            record_status(session, source, True)
        except (MarketDataError, Exception) as err:  # noqa: BLE001 — external source must never break the app
            log.warning("%s refresh failed: %s", code, err)
            result.errors.append(f"{code}: {err}")
            record_status(session, source, False, str(err))
    session.commit()
    return result


def refresh_all(
    session: Session, provider: MarketDataProvider, rates: RatesProvider, today: date | None = None
) -> RefreshResult:
    today = today or date.today()
    prices = refresh_prices(session, provider, today)
    bench = refresh_benchmarks(session, provider, rates, today)
    return RefreshResult(
        prices_inserted=prices.prices_inserted,
        benchmarks_inserted=bench.benchmarks_inserted,
        errors=prices.errors + bench.errors,
        tickers_without_data=prices.tickers_without_data,
    )


def load_price_book(session: Session) -> PriceBook:
    closes: dict[str, dict[date, Decimal]] = {}
    for ticker, day, close in session.execute(
        select(PriceHistory.ticker, PriceHistory.date, PriceHistory.close)
    ):
        closes.setdefault(ticker, {})[day] = close
    return PriceBook(closes)


@dataclass(frozen=True)
class Quote:
    date: date
    close: Decimal
    previous_close: Decimal | None


def latest_quotes(session: Session) -> dict[str, Quote]:
    ranked = select(
        PriceHistory.ticker,
        PriceHistory.date,
        PriceHistory.close,
        func.row_number()
        .over(partition_by=PriceHistory.ticker, order_by=PriceHistory.date.desc())
        .label("rn"),
    ).subquery()
    rows = session.execute(select(ranked).where(ranked.c.rn <= 2).order_by(ranked.c.ticker, ranked.c.rn))
    quotes: dict[str, Quote] = {}
    for ticker, day, close, rn in rows:
        if rn == 1:
            quotes[ticker] = Quote(day, close, None)
        else:
            quotes[ticker] = Quote(quotes[ticker].date, quotes[ticker].close, close)
    return quotes


def benchmark_series(session: Session, code: str) -> list[tuple[date, Decimal]]:
    rows = session.execute(
        select(BenchmarkHistory.date, BenchmarkHistory.value)
        .where(BenchmarkHistory.code == code)
        .order_by(BenchmarkHistory.date)
    )
    return [(day, value) for day, value in rows]


def source_statuses(session: Session) -> list[DataSourceStatus]:
    return list(session.scalars(select(DataSourceStatus).order_by(DataSourceStatus.source)))
