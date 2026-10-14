import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.report import DispatchOut  # noqa: F401 — re-exported for the watchlist router


class WatchItemOut(BaseModel):
    ticker: str
    name: str | None
    note: str | None
    price: Decimal | None
    sma: Decimal | None
    distance: Decimal | None  # fraction: price / SMA − 1
    zone: str | None  # CHEAP | BELOW | ABOVE | EXPENSIVE; None → less history than the SMA
    sessions: int
    price_date: dt.date | None


class WatchlistOut(BaseModel):
    items: list[WatchItemOut]
    channel: str | None  # SEPARATE | SHARED | None (no webhook)
    report_time: str
    sma_days: int
    cheap: Decimal
    expensive: Decimal
    last_scheduled: dt.date | None


class WatchItemIn(BaseModel):
    ticker: str = Field(min_length=4, max_length=12)
    note: str | None = Field(default=None, max_length=300)


class WatchItemPatch(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class WatchlistPreviewOut(BaseModel):
    date: dt.date
    content: str
    messages: list[str]
    channel: str | None
