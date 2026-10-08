import datetime as dt

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Number


class IndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    value: Number | None
    unit: str
    note: str | None


class FundamentalsOut(BaseModel):
    ticker: str
    cnpj: str
    name: str
    sector: str | None
    special_sector: str | None
    template: str | None
    price: Number | None
    price_date: dt.date | None
    shares_outstanding: Number | None
    shares_source: str | None
    profitable_years: int
    years_available: int
    last_dfp: dt.date | None
    last_itr: dt.date | None
    received_on: dt.date | None
    indicators: list[IndicatorOut]
    notes: list[str]


class IngestOut(BaseModel):
    started: bool
    message: str
