"""Keeps price_history and benchmark_history up to date. External failures are recorded in
data_source_status and never raised to the caller: the app keeps working with the cached data."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.market_data.base import MarketDataError, MarketDataProvider, RatesProvider
from app.models import BenchmarkHistory, DataSourceStatus, PriceHistory, Transaction
from app.portfolio.performance import PriceBook

log = logging.getLogger(__name__)

IBOV, CDI = "IBOV", "CDI"
IBOV_SYMBOL = "^BVSP"
SOURCE_PRICES, SOURCE_IBOV, SOURCE_CDI = "prices", "ibov", "cdi"
# Fetch a few days before the first trade so the first valuation has a close to fall back on
_LOOKBACK = timedelta(days=7)


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


def _last_dates(session: Session) -> dict[str, date]:
    rows = session.execute(
        select(PriceHistory.ticker, func.max(PriceHistory.date)).group_by(PriceHistory.ticker)
    )
    return dict(rows.all())


def refresh_prices(session: Session, provider: MarketDataProvider, today: date) -> RefreshResult:
    result = RefreshResult()
    last = _last_dates(session)
    failed: list[str] = []
    for ticker, first_day in sorted(tracked_tickers(session).items()):
        start = last[ticker] + timedelta(days=1) if ticker in last else first_day - _LOOKBACK
        if start > today:
            continue
        try:
            bars = provider.daily_bars([ticker], start, today).get(ticker, [])
        except MarketDataError as err:
            failed.append(ticker)
            log.warning("prices for %s failed: %s", ticker, err)
            continue
        if not bars and ticker not in last:
            result.tickers_without_data.append(ticker)
        for bar in bars:
            stmt = insert(PriceHistory).values(
                ticker=ticker,
                date=bar.date,
                close=bar.close,
                close_adjusted=bar.close_adjusted,
                volume=bar.volume,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                source=provider.name,
            )
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_={
                        "close": stmt.excluded.close,
                        "close_adjusted": stmt.excluded.close_adjusted,
                        "volume": stmt.excluded.volume,
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "source": stmt.excluded.source,
                    },
                )
            )
            result.prices_inserted += 1
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
