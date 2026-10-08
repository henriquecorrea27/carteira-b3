import datetime as dt

from pydantic import BaseModel, ConfigDict

from app.portfolio.types import AssetClass
from app.schemas.common import Money, Number

# Percentages travel as fractions ("0.1234" = 12,34%)


class _FromAttrs(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PositionOut(_FromAttrs):
    ticker: str
    name: str | None
    asset_class: AssetClass
    sector: str | None
    quantity: Number
    avg_price: Number
    total_cost: Money
    realized_result: Money
    provents_net: Money
    provents_net_12m: Money
    provents_receivable_net: Money
    # Cost attributed to a bonus is still unknown → PM is provisional
    pending_bonus_cost: bool
    first_date: dt.date | None
    current_price: Number | None
    price_date: dt.date | None
    day_change_pct: Number | None
    market_value: Money | None
    open_result: Money | None
    open_result_pct: Number | None
    weight_pct: Number | None
    yield_on_cost_pct: Number | None


class PortfolioSummaryOut(_FromAttrs):
    invested: Money
    market_value: Money
    open_result: Money
    open_result_pct: Number | None
    realized_result: Money
    provents_net_total: Money
    provents_net_12m: Money
    provents_receivable: Money
    total_result: Money
    return_total: Number | None
    return_12m: Number | None
    ibov_12m: Number | None
    cdi_12m: Number | None
    day_change: Money | None
    open_positions: int
    pending_bonus_cost: int
    prices_as_of: dt.date | None
    missing_prices: list[str]


class HistoryPointOut(_FromAttrs):
    date: dt.date
    invested: Money
    market_value: Money
    portfolio_return: Number
    ibov_return: Number | None
    cdi_return: Number | None


class AllocationSliceOut(_FromAttrs):
    key: str
    label: str
    value: Money
    pct: Number


class AllocationOut(BaseModel):
    by_class: list[AllocationSliceOut]
    by_sector: list[AllocationSliceOut]
    by_asset: list[AllocationSliceOut]


class AssetOut(BaseModel):
    ticker: str
    name: str | None
    asset_class: AssetClass
    class_confirmed: bool
    sector: str | None


class AssetPatch(BaseModel):
    name: str | None = None
    asset_class: AssetClass | None = None
    sector_override: str | None = None


class ProventOut(_FromAttrs):
    id: int
    ticker: str
    asset_class: AssetClass
    type: str
    status: str
    record_date: dt.date
    payment_date: dt.date | None
    quantity: Number
    value_per_share: Number | None
    gross_amount: Money
    tax_withheld: Money
    net_amount: Money
    source: str


class MonthBucketOut(_FromAttrs):
    month: str
    received: Money
    receivable: Money


class YearRowOut(_FromAttrs):
    year: int
    months: list[Money]
    total: Money
    monthly_avg: Money


class AssetShareOut(_FromAttrs):
    ticker: str
    net_amount: Money
    pct: Number


class ProventsSummaryOut(_FromAttrs):
    total_received: Money
    received_12m: Money
    monthly_avg_12m: Money
    receivable: Money
    monthly: list[MonthBucketOut]
    by_year: list[YearRowOut]
    by_asset_12m: list[AssetShareOut]
    upcoming: list[ProventOut]


class DataSourceStatusOut(_FromAttrs):
    source: str
    ok: bool
    message: str | None
    last_attempt_at: dt.datetime | None
    last_success_at: dt.datetime | None


class RefreshOut(BaseModel):
    prices_inserted: int
    benchmarks_inserted: int
    errors: list[str]
    tickers_without_data: list[str]
