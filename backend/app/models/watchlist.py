from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class WatchlistItem(TimestampMixin, Base):
    """A ticker the user follows outside the portfolio: alerted on Discord by its distance from the SMA200."""

    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), unique=True)
    note: Mapped[str | None] = mapped_column(Text)
