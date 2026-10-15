"""Runs the rule engine for a ticker or for the whole portfolio and keeps the daily history of decisions
(analysis_snapshots)."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.fundamentals import service as fundamentals
from app.fundamentals.indicators import apply_year_prices
from app.market_data.base import MarketDataError
from app.models import AnalysisSnapshot, CompanyTicker, PriceHistory, Transaction
from app.portfolio.engine import build_portfolio
from app.rules.engine import Analysis, evaluate, load_rules
from app.rules.technical import Technical, compute_technical
from app.schemas.analysis import analysis_details

log = logging.getLogger(__name__)
CHART_DAYS = 730  # default chart window (the 200-day SMA needs ~290 calendar days)
HISTORY_DAYS = (
    6 * 365 + 31
)  # synced once a day: year-end closes of the indicator history (6 DFPs) and the 5y chart

# (database, ticker) → (day, days) of its last re-sync with the provider (once a day per process is enough,
# unless a longer history is asked for later that day). Per database: each profile has its own price cache.
_synced: dict[tuple[str, str], tuple[date, int]] = {}


@dataclass
class TickerAnalysis:
    fundamentals: fundamentals.TickerFundamentals
    analysis: Analysis
    technical: Technical | None = None


def analyze(
    session: Session, ticker: str, market=None, events=None, today: date | None = None
) -> TickerAnalysis:
    today = today or date.today()
    tf = fundamentals.fundamentals_for(session, ticker, market, events, today)
    sync_history(session, tf.ticker, market, today)
    years = [row.year for row in tf.result.history if row.year is not None]
    apply_year_prices(tf.result, fundamentals.year_end_prices(session, tf.ticker, years))
    cfg = load_rules()
    technical = technical_for(session, tf.ticker, market, today, cfg)
    analysis = evaluate(tf.result, cfg, technical.score if technical else None)
    result = TickerAnalysis(tf, analysis, technical)
    save_snapshot(session, result, today)
    return result


def sync_history(session: Session, ticker: str, market, today: date, days: int = HISTORY_DAYS) -> None:
    """Fetches the last `days` of daily bars once a day per ticker: fills gaps (history older than the
    ~2 months cached for the liquidity) and re-syncs the split-adjusted closes. Failure keeps the cache."""
    key = (session.get_bind().url.render_as_string(), ticker)
    done = _synced.get(key)
    if market is None or (done is not None and done[0] == today and done[1] >= days):
        return
    try:
        fundamentals.fetch_range(session, market, ticker, today - timedelta(days=days), today, resync=True)
    except MarketDataError as err:
        log.warning("price history for %s failed: %s", ticker, err)
        return
    _synced[key] = (today, days)


def technical_for(session: Session, ticker: str, market, today: date, cfg: dict) -> Technical | None:
    """Chart analysis (F8) on the split-adjusted daily closes, like any chart site."""
    tech_cfg = cfg.get("technical") or {}
    if not tech_cfg.get("enabled"):
        return None
    sync_history(session, ticker, market, today)
    return compute_technical(adjusted_closes(session, ticker, today, int(tech_cfg["sma_days"])), tech_cfg)


def adjusted_closes(session: Session, ticker: str, today: date, limit: int) -> list[Decimal]:
    """The last `limit` split-adjusted daily closes up to `today`, oldest first."""
    closes = session.scalars(
        select(PriceHistory.close_adjusted)
        .where(PriceHistory.ticker == ticker, PriceHistory.date <= today)
        .order_by(PriceHistory.date.desc())
        .limit(limit)
    ).all()
    return list(reversed(closes))


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


@dataclass(frozen=True)
class Bar:
    date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    volume: Decimal | None


def price_bars(
    session: Session, ticker: str, market=None, today: date | None = None, days: int = CHART_DAYS
) -> list[Bar]:
    """Daily bars for the chart, split-adjusted (same basis as the SMA of the chart analysis)."""
    today = today or date.today()
    sync_history(session, ticker, market, today, max(days, HISTORY_DAYS))
    fundamentals.ensure_recent_prices(session, market, [ticker], today)
    rows = session.scalars(
        select(PriceHistory)
        .where(PriceHistory.ticker == ticker, PriceHistory.date >= today - timedelta(days=days))
        .order_by(PriceHistory.date)
    )
    bars = []
    for r in rows:
        k = r.close_adjusted / r.close if r.close else Decimal(1)  # split factor: raw OHLC → adjusted
        bars.append(
            Bar(
                r.date,
                r.open * k if r.open is not None else None,
                r.high * k if r.high is not None else None,
                r.low * k if r.low is not None else None,
                r.close_adjusted,
                r.volume / k if r.volume is not None and k else None,
            )
        )
    return bars
