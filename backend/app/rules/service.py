"""Runs the rule engine for a ticker or for the whole portfolio and keeps the daily history of decisions
(analysis_snapshots)."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.fundamentals import service as fundamentals
from app.market_data.base import MarketDataError
from app.models import AnalysisSnapshot, CompanyTicker, PriceHistory, Transaction
from app.portfolio.engine import build_portfolio
from app.rules.engine import Analysis, evaluate
from app.schemas.analysis import analysis_details

log = logging.getLogger(__name__)
CHART_DAYS = 730


@dataclass
class TickerAnalysis:
    fundamentals: fundamentals.TickerFundamentals
    analysis: Analysis


def analyze(
    session: Session, ticker: str, market=None, events=None, today: date | None = None
) -> TickerAnalysis:
    today = today or date.today()
    tf = fundamentals.fundamentals_for(session, ticker, market, events, today)
    result = TickerAnalysis(tf, evaluate(tf.result))
    save_snapshot(session, result, today)
    return result


def save_snapshot(session: Session, ta: TickerAnalysis, today: date) -> None:
    a, r = ta.analysis, ta.fundamentals.result
    values = {
        "ticker": ta.fundamentals.ticker,
        "date": today,
        "decision": a.decision.value,
        "score_final": a.score_final,
        "score_quality": a.score_quality,
        "score_price": a.score_price,
        "inconclusive": a.quality_inconclusive or a.price_inconclusive,
        "main_reason": a.main_reason,
        "special_sector": a.special_sector,
        "price": ta.fundamentals.price,
        "last_dfp": r.last_dfp,
        "last_itr": r.last_itr,
        "rules_version": a.rules_version,
        "details": analysis_details(ta),
    }
    stmt = insert(AnalysisSnapshot).values(**values)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={k: getattr(stmt.excluded, k) for k in values if k not in ("ticker", "date")},
        )
    )
    session.commit()


@dataclass
class PortfolioRun:
    analyzed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # FIIs, ETFs, BDRs, unknown tickers
    errors: list[str] = field(default_factory=list)


def portfolio_stock_tickers(session: Session) -> list[str]:
    entries = [t.to_entry() for t in session.scalars(select(Transaction))]
    held = sorted(p.ticker for p in build_portfolio(entries).open_positions)
    listed = set(session.scalars(select(CompanyTicker.ticker).where(CompanyTicker.ticker.in_(held))))
    return [t for t in held if t in listed]


def analyze_portfolio(session: Session, market=None, events=None, today: date | None = None) -> PortfolioRun:
    today = today or date.today()
    run = PortfolioRun()
    entries = [t.to_entry() for t in session.scalars(select(Transaction))]
    held = sorted(p.ticker for p in build_portfolio(entries).open_positions)
    stocks = set(portfolio_stock_tickers(session))
    for ticker in held:
        if ticker not in stocks:
            run.skipped.append(ticker)
            continue
        try:
            analyze(session, ticker, market, events, today)
            run.analyzed.append(ticker)
        except Exception as err:  # noqa: BLE001 — one ticker must not stop the others
            session.rollback()
            log.exception("analysis of %s failed", ticker)
            run.errors.append(f"{ticker}: {err}")
    return run


def latest_snapshots(session: Session, tickers: list[str] | None = None) -> dict[str, AnalysisSnapshot]:
    latest = select(AnalysisSnapshot.ticker, func.max(AnalysisSnapshot.date).label("d")).group_by(
        AnalysisSnapshot.ticker
    )
    if tickers is not None:
        latest = latest.where(AnalysisSnapshot.ticker.in_(tickers))
    sub = latest.subquery()
    rows = session.scalars(
        select(AnalysisSnapshot).join(
            sub, (AnalysisSnapshot.ticker == sub.c.ticker) & (AnalysisSnapshot.date == sub.c.d)
        )
    )
    return {s.ticker: s for s in rows}


@dataclass(frozen=True)
class DecisionChange:
    ticker: str
    previous: str
    current: str
    previous_date: date
    current_date: date


def decision_changes(session: Session, day: date) -> list[DecisionChange]:
    """Tickers whose decision on `day` differs from their previous snapshot (used by the daily report)."""
    changes = []
    for snap in session.scalars(select(AnalysisSnapshot).where(AnalysisSnapshot.date == day)):
        before = session.scalar(
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.ticker == snap.ticker, AnalysisSnapshot.date < day)
            .order_by(AnalysisSnapshot.date.desc())
            .limit(1)
        )
        if before is not None and before.decision != snap.decision:
            changes.append(DecisionChange(snap.ticker, before.decision, snap.decision, before.date, day))
    return changes


def price_bars(session: Session, ticker: str, market=None, today: date | None = None, days: int = CHART_DAYS):
    """Daily bars for the chart, fetching the missing history once (cached in price_history)."""
    today = today or date.today()
    start = today - timedelta(days=days)
    first = session.scalar(select(func.min(PriceHistory.date)).where(PriceHistory.ticker == ticker))
    if market is not None and (first is None or first > start + timedelta(days=7)):
        try:
            fundamentals.fetch_range(
                session, market, ticker, start, (first - timedelta(days=1)) if first else today
            )
        except MarketDataError as err:  # chart falls back to whatever is cached
            log.warning("price history for %s failed: %s", ticker, err)
    fundamentals.ensure_recent_prices(session, market, [ticker], today)
    missing_ohlc = session.scalar(
        select(func.min(PriceHistory.date)).where(
            PriceHistory.ticker == ticker, PriceHistory.date >= start, PriceHistory.open.is_(None)
        )
    )
    if market is not None and missing_ohlc is not None:
        try:
            fundamentals.fetch_range(session, market, ticker, missing_ohlc, today, fill_ohlc=True)
        except MarketDataError as err:
            log.warning("OHLC backfill for %s failed: %s", ticker, err)
    return list(
        session.scalars(
            select(PriceHistory)
            .where(PriceHistory.ticker == ticker, PriceHistory.date >= start)
            .order_by(PriceHistory.date)
        )
    )
