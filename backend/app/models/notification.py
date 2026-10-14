import datetime as dt

from sqlalchemy import Boolean, Date, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class ReportDispatch(TimestampMixin, Base):
    """Every attempt to send a report (`kind`: the DAILY report or the WATCHLIST alert). A SENT row with
    trigger SCHEDULED marks the day as done for its kind (catch-up and no duplicates); its `decisions` are the
    baseline for the next report's changes (DAILY: ticker → decision; WATCHLIST: ticker → SMA200 zone)."""

    __tablename__ = "report_dispatches"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[dt.date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(10), default="DAILY", server_default="DAILY")
    trigger: Mapped[str] = mapped_column(String(10))  # SCHEDULED | MANUAL
    status: Mapped[str] = mapped_column(String(10))  # SENT | FAILED
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    channel: Mapped[str] = mapped_column(String(20))
    messages: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    decisions: Mapped[dict] = mapped_column(JSONB, default=dict)  # ticker -> BUY | WAIT | AVOID
    content: Mapped[str] = mapped_column(Text)
