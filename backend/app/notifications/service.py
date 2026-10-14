"""Sending the daily report and the watchlist alert: which day is due (catch-up), the send log (no duplicates,
one per kind) and the manual send."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ReportDispatch, WatchlistItem
from app.notifications.base import Notifier, NotifierError, split_message
from app.notifications.discord import DiscordNotifier
from app.notifications.report import build_report, is_business_day, last_business_day, render
from app.notifications.watchlist import build_watchlist, render_watchlist

log = logging.getLogger(__name__)
SCHEDULED, MANUAL = "SCHEDULED", "MANUAL"
SENT, FAILED = "SENT", "FAILED"
DAILY, WATCHLIST = "DAILY", "WATCHLIST"
# A scheduled report sent more than this after the configured time is marked as late
LATE_AFTER = timedelta(hours=2)
# pg advisory locks: one run of each kind at a time (OS scheduler + UI button)
_LOCK_KEYS = {DAILY: 74_201_001, WATCHLIST: 74_201_002}


def local_now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone)).replace(tzinfo=None)


def report_time() -> time:
    hours, minutes = get_settings().report_time.split(":")
    return time(int(hours), int(minutes))


def get_notifier() -> Notifier | None:
    url = get_settings().discord_webhook_url.strip()
    return DiscordNotifier(url) if url else None


def watchlist_channel() -> str | None:
    """SEPARATE: its own webhook · SHARED: the daily report's channel · None: no webhook at all."""
    settings = get_settings()
    if settings.discord_watchlist_webhook_url.strip():
        return "SEPARATE"
    return "SHARED" if settings.discord_webhook_url.strip() else None


def get_watchlist_notifier() -> Notifier | None:
    settings = get_settings()
    url = settings.discord_watchlist_webhook_url.strip() or settings.discord_webhook_url.strip()
    return DiscordNotifier(url, username="Carteira B3 · MM200") if url else None


def has_watchlist(session: Session) -> bool:
    return bool(session.scalar(select(exists().where(WatchlistItem.id.isnot(None)))))


def due_report_date(now: datetime, at: time) -> date:
    """Latest B3 business day whose report time has already passed."""
    day = now.date()
    if not is_business_day(day) or now.time() < at:
        day = last_business_day(day - timedelta(days=1))
    return day


def last_sent(session: Session, before: date | None = None, kind: str = DAILY) -> ReportDispatch | None:
    query = select(ReportDispatch).where(
        ReportDispatch.kind == kind, ReportDispatch.trigger == SCHEDULED, ReportDispatch.status == SENT
    )
    if before is not None:
        query = query.where(ReportDispatch.report_date < before)
    query = query.order_by(ReportDispatch.report_date.desc(), ReportDispatch.id.desc())
    return session.scalar(query.limit(1))


def already_sent(session: Session, day: date, kind: str = DAILY) -> bool:
    return (
        session.scalar(
            select(ReportDispatch.id).where(
                ReportDispatch.kind == kind,
                ReportDispatch.trigger == SCHEDULED,
                ReportDispatch.status == SENT,
                ReportDispatch.report_date == day,
            )
        )
        is not None
    )


def compose(session: Session, day: date, now: datetime, late: bool = False):
    """Builds the report for `day` against the last scheduled report sent before it."""
    previous = last_sent(session, before=day)
    report = build_report(
        session,
        day,
        now,
        baseline=previous.decisions if previous else None,
        paid_since=previous.report_date if previous else None,
        late=late,
    )
    return report, render(report)


def send_report(
    session: Session, notifier: Notifier, day: date, now: datetime, trigger: str, late: bool = False
) -> ReportDispatch:
    report, content = compose(session, day, now, late)
    return _dispatch(session, notifier, DAILY, day, trigger, late, report.decisions, content)


def compose_watchlist(session: Session, day: date, now: datetime, market=None, late: bool = False):
    """Builds the watchlist alert for `day` against the zones of the last scheduled alert sent before it."""
    previous = last_sent(session, before=day, kind=WATCHLIST)
    report = build_watchlist(
        session, day, now, baseline=previous.decisions if previous else None, market=market, late=late
    )
    return report, render_watchlist(report)


def send_watchlist(
    session: Session,
    notifier: Notifier,
    day: date,
    now: datetime,
    trigger: str,
    market=None,
    late: bool = False,
) -> ReportDispatch:
    report, content = compose_watchlist(session, day, now, market, late)
    return _dispatch(session, notifier, WATCHLIST, day, trigger, late, report.zones, content)


def _dispatch(
    session: Session,
    notifier: Notifier,
    kind: str,
    day: date,
    trigger: str,
    late: bool,
    decisions: dict,
    content: str,
) -> ReportDispatch:
    messages = split_message(content, notifier.max_length)
    dispatch = ReportDispatch(
        report_date=day,
        kind=kind,
        trigger=trigger,
        late=late,
        channel=notifier.name,
        messages=len(messages),
        decisions=decisions,
        content=content,
    )
    try:
        notifier.send(messages)
        dispatch.status = SENT
    except NotifierError as err:
        dispatch.status, dispatch.error = FAILED, str(err)
        log.warning("%s report for %s not sent: %s", kind.lower(), day, err)
    session.add(dispatch)
    session.commit()
    return dispatch


@dataclass
class ScheduledRun:
    status: str  # SENT | FAILED | ALREADY_SENT | NOT_CONFIGURED | BUSY | EMPTY (watchlist without tickers)
    day: date | None = None
    late: bool = False
    error: str | None = None
    refresh_errors: list[str] = field(default_factory=list)


def run_scheduled(
    session: Session,
    notifier: Notifier | None,
    now: datetime | None = None,
    refresh: Callable[[Session], list[str]] | None = None,
    force: bool = False,
    kind: str = DAILY,
    market=None,
) -> ScheduledRun:
    """Sends the due report of `kind` once (catch-up: a missed day is sent at the next run, marked as late).
    `refresh` updates prices/events/decisions first and returns its errors (they never stop the report).
    The watchlist re-syncs its own price history with `market` and is skipped while the list is empty."""
    now = now or local_now()
    at = report_time()
    day = due_report_date(now, at)
    if notifier is None:
        return ScheduledRun("NOT_CONFIGURED", day)
    with session.get_bind().connect() as lock_conn:
        key = _LOCK_KEYS[kind]
        if not lock_conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}):
            return ScheduledRun("BUSY", day)
        try:
            if already_sent(session, day, kind) and not force:
                return ScheduledRun("ALREADY_SENT", day)
            if kind == WATCHLIST and not has_watchlist(session):
                return ScheduledRun("EMPTY", day)
            errors = refresh(session) if refresh else []
            late = now > datetime.combine(day, at) + LATE_AFTER
            if kind == WATCHLIST:
                dispatch = send_watchlist(session, notifier, day, now, SCHEDULED, market, late)
            else:
                dispatch = send_report(session, notifier, day, now, SCHEDULED, late)
            return ScheduledRun(dispatch.status, day, late, dispatch.error, errors)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            lock_conn.commit()


def manual_day(now: datetime) -> date:
    return last_business_day(now.date())


def recent_dispatches(session: Session, limit: int = 10, kind: str = DAILY) -> list[ReportDispatch]:
    return list(
        session.scalars(
            select(ReportDispatch)
            .where(ReportDispatch.kind == kind)
            .order_by(ReportDispatch.created_at.desc())
            .limit(limit)
        )
    )
