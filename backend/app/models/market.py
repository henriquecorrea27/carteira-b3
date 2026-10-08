import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class PriceHistory(TimestampMixin, Base):
    """Daily close per ticker, in RAW terms (not split-adjusted) so it matches the share counts the
    ledger had on that day. `close_adjusted` keeps the provider's split-adjusted value for reference."""

    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("ticker", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), index=True)
    date: Mapped[dt.date] = mapped_column(Date)
    close: Mapped[Decimal]
    close_adjusted: Mapped[Decimal]
    volume: Mapped[Decimal | None]
    open: Mapped[Decimal | None]
    high: Mapped[Decimal | None]
    low: Mapped[Decimal | None]
    source: Mapped[str] = mapped_column(String(20))


class BenchmarkHistory(TimestampMixin, Base):
    """IBOV: index close. CDI: daily rate in % per day (BCB SGS series 12)."""

    __tablename__ = "benchmark_history"
    __table_args__ = (UniqueConstraint("code", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10))
    date: Mapped[dt.date] = mapped_column(Date)
    value: Mapped[Decimal]


class DataSourceStatus(Base):
    """Last run of each external source, shown as a warning in the UI when it failed."""

    __tablename__ = "data_source_status"

    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(default=True)
    message: Mapped[str | None] = mapped_column(Text)
