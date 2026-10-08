from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class DailyBar:
    date: date
    close: Decimal  # raw close (as traded that day)
    close_adjusted: Decimal  # provider's split-adjusted close
    volume: Decimal | None


class MarketDataError(Exception):
    pass


class MarketDataProvider(Protocol):
    name: str

    def daily_bars(self, tickers: list[str], start: date, end: date) -> dict[str, list[DailyBar]]:
        """Daily bars for B3 tickers (without the .SA suffix), start/end inclusive.
        Tickers without data are simply missing from the result."""
        ...

    def index_closes(self, symbol: str, start: date, end: date) -> list[tuple[date, Decimal]]: ...


class RatesProvider(Protocol):
    name: str

    def cdi_daily(self, start: date, end: date) -> list[tuple[date, Decimal]]:
        """CDI daily rate in % per day."""
        ...
