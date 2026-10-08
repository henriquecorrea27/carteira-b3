from datetime import date

from pydantic import BaseModel

from app.portfolio.types import AssetClass
from app.schemas.common import Money, Number


class PositionOut(BaseModel):
    ticker: str
    name: str | None
    asset_class: AssetClass
    sector: str | None
    quantity: Number
    avg_price: Number
    total_cost: Money
    realized_result: Money
    provents_net: Money
    provents_receivable_net: Money
    # Cost attributed to a bonus is still unknown → PM is provisional
    pending_bonus_cost: bool
    first_date: date | None
    # Filled from F2 on (market prices)
    current_price: Number | None = None
    market_value: Money | None = None


class PortfolioSummaryOut(BaseModel):
    invested: Money
    realized_result: Money
    provents_net_total: Money
    provents_net_12m: Money
    provents_receivable: Money
    open_positions: int
    pending_bonus_cost: int
    # Filled from F2 on
    market_value: Money | None = None
    open_result: Money | None = None


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
