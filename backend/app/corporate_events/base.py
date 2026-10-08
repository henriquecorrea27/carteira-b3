from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class ParsedEvent:
    event_key: str
    issuer: str
    isin: str
    ticker: str | None
    category: str  # CASH | STOCK | OTHER
    label: str
    tx_type: str | None
    record_date: date
    ex_date: date
    payment_date: date | None
    value: Decimal
    factor: Decimal | None
    approved_on: date | None
    related_to: str | None
    remarks: str | None


class CorporateEventsError(Exception):
    pass


class CorporateEventsSource(Protocol):
    name: str

    def events_for_issuer(self, issuer: str) -> list[ParsedEvent]:
        """Provents and stock events of one issuer (first 4 letters of the ticker)."""
        ...
