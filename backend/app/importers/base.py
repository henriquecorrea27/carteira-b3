"""Common types for portfolio importers. Each importer turns one exported file into candidate rows;
app.importers.service resolves them against the ledger, deduplicates and saves."""

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.portfolio.types import ProventStatus, TransactionType


class RowStatus(StrEnum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"  # already imported (same dedup hash)
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"  # looks like an existing manual entry; needs confirmation
    IGNORED = "IGNORED"  # out of scope (futures, fixed income, settlement lines, ...)
    ERROR = "ERROR"


@dataclass
class Candidate:
    """A transaction proposed by an importer, before ledger-dependent resolution."""

    date: date
    ticker: str
    type: TransactionType
    quantity: Decimal = Decimal(0)
    price: Decimal | None = None
    broker: str | None = None
    gross_amount: Decimal | None = None
    tax_withheld: Decimal | None = None
    payment_date: date | None = None
    status: ProventStatus | None = None
    # B3 movement semantics, resolved into a factor later:
    # SPLIT → new shares credited; REVERSE_SPLIT → resulting position
    credited_quantity: Decimal | None = None
    factor: Decimal | None = None
    notes: str | None = None
    asset_name: str | None = None


@dataclass
class ImportRow:
    file: str
    line: int  # spreadsheet row number (1 = header)
    raw: dict[str, str]
    status: RowStatus
    reason: str | None = None
    candidate: Candidate | None = None
    dedup_hash: str | None = None
    # Rows merged into another one (e.g. the same split credited at two brokers)
    merged_lines: list[int] = field(default_factory=list)


class PortfolioImporter(Protocol):
    name: str

    def matches(self, sheet_name: str, header: list[str]) -> bool: ...

    def parse(self, file_name: str, rows: list[list[Any]]) -> list[ImportRow]: ...


def to_decimal(value: Any) -> Decimal | None:
    """B3 exports store numbers as int/float cells and empty values as '-'."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text in ("", "-"):
            return None
        return Decimal(text.replace(".", "").replace(",", ".")) if "," in text else Decimal(text)
    if isinstance(value, float):
        # repr() gives the shortest decimal that round-trips (19.233, not 19.23299999…)
        return Decimal(repr(value))
    return Decimal(value)


def to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()


def normalize_broker(name: str | None) -> str | None:
    if not name:
        return None
    return " ".join(name.strip().rstrip(".").upper().split())


def row_hash(*parts: Any) -> str:
    text = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)
