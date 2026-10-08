import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.portfolio.engine import LedgerEntry
from app.portfolio.types import ProventStatus, TransactionType


class Transaction(TimestampMixin, Base):
    """One row of the ledger. Positions, PM, realized results and provents are always derived
    from these rows (see app.portfolio.engine.LedgerEntry for the meaning of each field per type)."""

    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_ticker_date", "ticker", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Trade date, ex-date for corporate events, record date (data-com) for provents
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    ticker: Mapped[str] = mapped_column(String(12), ForeignKey("assets.ticker", onupdate="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(default=Decimal(0))
    price: Mapped[Decimal | None]
    costs: Mapped[Decimal] = mapped_column(default=Decimal(0))
    factor: Mapped[Decimal | None]
    target_ticker: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("assets.ticker", onupdate="CASCADE")
    )
    gross_amount: Mapped[Decimal | None]
    tax_withheld: Mapped[Decimal | None]
    net_amount: Mapped[Decimal | None]
    payment_date: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(12))
    broker: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10))
    # Manual edits always win: jobs never overwrite a row the user changed
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set for imported/automatic rows to make re-runs idempotent
    dedup_hash: Mapped[str | None] = mapped_column(String(64), unique=True)

    def to_entry(self) -> LedgerEntry:
        return LedgerEntry(
            date=self.date,
            ticker=self.ticker,
            type=TransactionType(self.type),
            quantity=self.quantity,
            price=self.price,
            costs=self.costs,
            factor=self.factor,
            target_ticker=self.target_ticker,
            gross_amount=self.gross_amount,
            tax_withheld=self.tax_withheld,
            net_amount=self.net_amount,
            payment_date=self.payment_date,
            status=ProventStatus(self.status) if self.status else None,
            id=self.id,
            seq=self.id or 0,
        )
