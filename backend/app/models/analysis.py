import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, Date, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class AnalysisSnapshot(TimestampMixin, Base):
    """Daily rule-engine result per ticker (one row per ticker and day), used to show the decision in
    the portfolio and to detect decision changes for the daily report."""

    __tablename__ = "analysis_snapshots"
    __table_args__ = (UniqueConstraint("ticker", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    decision: Mapped[str] = mapped_column(String(8))
    score_final: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    score_quality: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    score_price: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    inconclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    main_reason: Mapped[str | None] = mapped_column(Text)
    special_sector: Mapped[str | None] = mapped_column(String(12))
    price: Mapped[Decimal | None]
    last_dfp: Mapped[dt.date | None] = mapped_column(Date)
    last_itr: Mapped[dt.date | None] = mapped_column(Date)
    rules_version: Mapped[int] = mapped_column(Integer)
    # Full explained analysis (indicators, ranges, points, eliminatory checks) as shown in the UI
    details: Mapped[dict] = mapped_column(JSONB)
