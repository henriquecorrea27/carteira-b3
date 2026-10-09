"""Sending the daily report: which day is due (catch-up), the send log (no duplicates) and the manual send."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ReportDispatch
from app.notifications.base import Notifier, NotifierError, split_message
from app.notifications.discord import DiscordNotifier
from app.notifications.report import build_report, is_business_day, last_business_day, render

log = logging.getLogger(__name__)
SCHEDULED, MANUAL = "SCHEDULED", "MANUAL"
SENT, FAILED = "SENT", "FAILED"
# A scheduled report sent more than this after the configured time is marked as late
LATE_AFTER = timedelta(hours=2)
_LOCK_KEY = 74_201_001  # pg advisory lock: one report run at a time (OS scheduler + UI button)


def local_now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone)).replace(tzinfo=None)


def report_time() -> time:
    hours, minutes = get_settings().report_time.split(":")
    return time(int(hours), int(minutes))


def get_notifier() -> Notifier | None:
    url = get_settings().discord_webhook_url.strip()
    return DiscordNotifier(url) if url else None


def due_report_date(now: datetime, at: time) -> date:
    """Latest B3 business day whose report time has already passed."""
    day = now.date()
    if not is_business_day(day) or now.time() < at:
        day = last_business_day(day - timedelta(days=1))
    return day


def last_sent(session: Session, before: date | None = None) -> ReportDispatch | None:
    query = select(ReportDispatch).where(ReportDispatch.trigger == SCHEDULED, ReportDispatch.status == SENT)
    if before is not None:
        query = query.where(ReportDispatch.report_date < before)
    query = query.order_by(ReportDispatch.report_date.desc(), ReportDispatch.id.desc())
    return session.scalar(query.limit(1))


def already_sent(session: Session, day: date) -> bool:
    return (
        session.scalar(
            select(ReportDispatch.id).where(
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
    messages = split_message(content, notifier.max_length)
    dispatch = ReportDispatch(
        report_date=day,
        trigger=trigger,
        late=late,
        channel=notifier.name,
        messages=len(messages),
        decisions=report.decisions,
        content=content,
    )
    try:
        notifier.send(messages)
        dispatch.status = SENT
    except NotifierError as err:
        dispatch.status, dispatch.error = FAILED, str(err)
        log.warning("daily report for %s not sent: %s", day, err)
    session.add(dispatch)
    session.commit()
    return dispatch


@dataclass
class ScheduledRun:
    status: str  # SENT | FAILED | ALREADY_SENT | NOT_CONFIGURED | BUSY
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
) -> ScheduledRun:
    """Sends the due report once (catch-up: a missed day is sent at the next run, marked as late).
    `refresh` updates prices/events/decisions first and returns its errors (they never stop the report)."""
    now = now or local_now()
    at = report_time()
    day = due_report_date(now, at)
    if notifier is None:
        return ScheduledRun("NOT_CONFIGURED", day)
    with session.get_bind().connect() as lock_conn:
        if not lock_conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}):
            return ScheduledRun("BUSY", day)
        try:
            if already_sent(session, day) and not force:
                return ScheduledRun("ALREADY_SENT", day)
            errors = refresh(session) if refresh else []
            late = now > datetime.combine(day, at) + LATE_AFTER
            dispatch = send_report(session, notifier, day, now, SCHEDULED, late)
            return ScheduledRun(dispatch.status, day, late, dispatch.error, errors)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
            lock_conn.commit()


def manual_day(now: datetime) -> date:
    return last_business_day(now.date())


def recent_dispatches(session: Session, limit: int = 10) -> list[ReportDispatch]:
    return list(
        session.scalars(select(ReportDispatch).order_by(ReportDispatch.created_at.desc()).limit(limit))
    )
