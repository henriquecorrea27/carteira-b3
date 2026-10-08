import datetime as dt

from pydantic import BaseModel

from app.importers.base import RowStatus
from app.portfolio.types import TransactionType
from app.schemas.common import Money, Number


class ImportRowOut(BaseModel):
    file: str
    line: int
    status: RowStatus
    reason: str | None
    raw: dict[str, str]
    merged_lines: list[int]
    # Resolved transaction (present for NEW / POSSIBLE_DUPLICATE rows and for rows that failed validation)
    date: dt.date | None = None
    ticker: str | None = None
    type: TransactionType | None = None
    quantity: Number | None = None
    price: Number | None = None
    factor: Number | None = None
    gross_amount: Money | None = None
    tax_withheld: Money | None = None
    broker: str | None = None


class ImportReportOut(BaseModel):
    committed: bool
    files: dict[str, str]
    counts: dict[RowStatus, int]
    inserted: int
    rows: list[ImportRowOut]
