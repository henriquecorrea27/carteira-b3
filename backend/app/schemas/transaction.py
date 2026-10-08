from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.portfolio.tickers import normalize_ticker
from app.portfolio.types import (
    PROVENT_TYPES,
    ProventStatus,
    TransactionSource,
    TransactionType,
)
from app.schemas.common import Money, Number

T = TransactionType


class TransactionIn(BaseModel):
    """Manual entry (single or batch row). Field requirements depend on `type`."""

    date: date
    ticker: str
    type: TransactionType
    quantity: Decimal | None = Field(default=None, ge=0)
    price: Decimal | None = Field(default=None, ge=0)
    costs: Decimal = Field(default=Decimal(0), ge=0)
    factor: Decimal | None = Field(default=None, gt=0)
    target_ticker: str | None = None
    gross_amount: Decimal | None = Field(default=None, ge=0)
    tax_withheld: Decimal | None = Field(default=None, ge=0)
    payment_date: date | None = None
    status: ProventStatus | None = None
    broker: str | None = Field(default=None, max_length=120)
    notes: str | None = None

    @field_validator("ticker", "target_ticker")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        return normalize_ticker(value) if value else value

    @field_validator("broker", "notes")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @model_validator(mode="after")
    def _check_fields_for_type(self) -> "TransactionIn":
        missing = []
        match self.type:
            case T.BUY | T.SELL | T.FRACTION_AUCTION:
                if not self.quantity:
                    missing.append("quantidade")
                if self.price is None:
                    missing.append("preço")
            case T.SPLIT | T.REVERSE_SPLIT:
                if self.factor is None:
                    missing.append("fator")
            case T.BONUS:
                if not self.quantity:
                    missing.append("quantidade")
            case T.TICKER_CHANGE:
                if self.factor is None:
                    missing.append("fator")
                if not self.target_ticker:
                    missing.append("ticker de destino")
            case t if t in PROVENT_TYPES:
                if self.gross_amount is None and (not self.quantity or self.price is None):
                    missing.append("valor bruto (ou quantidade e valor por ação)")
        if missing:
            raise ValueError(f"campos obrigatórios para {self.type}: {', '.join(missing)}")
        if self.type not in PROVENT_TYPES and self.date > date.today():
            raise ValueError("a data do lançamento não pode estar no futuro")
        return self


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    ticker: str
    type: TransactionType
    quantity: Number
    price: Number | None
    costs: Money
    factor: Number | None
    target_ticker: str | None
    gross_amount: Money | None
    tax_withheld: Money | None
    net_amount: Money | None
    payment_date: date | None
    status: ProventStatus | None
    broker: str | None
    notes: str | None
    source: TransactionSource
    user_edited: bool
    created_at: datetime
    updated_at: datetime


class TransactionBatchIn(BaseModel):
    items: list[TransactionIn] = Field(min_length=1, max_length=500)


class LedgerIssue(BaseModel):
    """Validation error tied to a batch row (index) or to an existing transaction (id)."""

    code: str
    message: str
    row: int | None = None
    transaction_id: int | None = None
