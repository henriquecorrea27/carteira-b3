import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class CorporateEvent(TimestampMixin, Base):
    """Cache of provents and stock events published by the external source (B3 listed companies).
    Ledger transactions are generated from these rows by app.corporate_events.service.apply_events."""

    __tablename__ = "corporate_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(20))
    issuer: Mapped[str] = mapped_column(String(8), index=True)
    isin: Mapped[str] = mapped_column(String(12))
    # None when the ISIN is not a tradable class we map (receipts, rights, ...)
    ticker: Mapped[str | None] = mapped_column(String(12), index=True)
    category: Mapped[str] = mapped_column(String(10))  # CASH | STOCK | OTHER
    label: Mapped[str] = mapped_column(String(40))  # as published (DIVIDENDO, BONIFICACAO, ...)
    # Mapped TransactionType, None when the label is not supported yet
    tx_type: Mapped[str | None] = mapped_column(String(20))
    record_date: Mapped[dt.date] = mapped_column(Date)  # data-com (last day with rights)
    ex_date: Mapped[dt.date] = mapped_column(Date)
    payment_date: Mapped[dt.date | None] = mapped_column(Date)
    # Cash: value per share. Stock: published number (% of new shares, or new/old ratio for reverse splits)
    value: Mapped[Decimal]
    # Engine factor for SPLIT/REVERSE_SPLIT, fraction of new shares for BONUS
    factor: Mapped[Decimal | None]
    approved_on: Mapped[dt.date | None] = mapped_column(Date)
    related_to: Mapped[str | None] = mapped_column(String(80))
    remarks: Mapped[str | None] = mapped_column(Text)
    # The user deleted the transaction generated from this event: never generate it again
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
