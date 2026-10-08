from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.market_data import service as market
from app.market_data.bcb import BCBRatesProvider
from app.market_data.yfinance_provider import YFinanceProvider
from app.models import Asset
from app.portfolio import dashboard, provents
from app.portfolio.tickers import InvalidTickerError, normalize_ticker
from app.portfolio.types import AssetClass
from app.schemas.portfolio import (
    AllocationOut,
    AssetOut,
    AssetPatch,
    DataSourceStatusOut,
    HistoryPointOut,
    PortfolioSummaryOut,
    PositionOut,
    ProventOut,
    ProventsSummaryOut,
    RefreshOut,
)

router = APIRouter(tags=["portfolio"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_market_provider():
    return YFinanceProvider()


def get_rates_provider():
    return BCBRatesProvider()


@router.get("/portfolio/positions", response_model=list[PositionOut])
def positions(session: SessionDep, include_closed: bool = False):
    return dashboard.positions(dashboard.DashboardContext(session), include_closed)


@router.get("/portfolio/summary", response_model=PortfolioSummaryOut)
def summary(session: SessionDep):
    return dashboard.summary(dashboard.DashboardContext(session))


@router.get("/portfolio/history", response_model=list[HistoryPointOut])
def history(session: SessionDep, range: Literal["1m", "6m", "12m", "ytd", "5y", "all"] = "12m"):  # noqa: A002
    return dashboard.history(dashboard.DashboardContext(session), range)


@router.get("/portfolio/allocation", response_model=AllocationOut)
def allocation(session: SessionDep):
    slices = dashboard.allocation(dashboard.DashboardContext(session))
    return AllocationOut(by_class=slices["class"], by_sector=slices["sector"], by_asset=slices["asset"])


@router.get("/provents", response_model=list[ProventOut])
def list_provents(
    session: SessionDep,
    year: int | None = None,
    ticker: str | None = None,
    status: Literal["ANNOUNCED", "PAID", "CONFIRMED"] | None = None,
):
    if ticker:
        try:
            ticker = normalize_ticker(ticker)
        except InvalidTickerError:
            return []
    return provents.list_provents(dashboard.DashboardContext(session), year, ticker, status)


@router.get("/provents/summary", response_model=ProventsSummaryOut)
def provents_summary(session: SessionDep, months: int = 12):
    return provents.provents_summary(dashboard.DashboardContext(session), months_back=max(1, min(months, 60)))


@router.post("/market-data/refresh", response_model=RefreshOut)
def refresh_market_data(
    session: SessionDep,
    provider: Annotated[object, Depends(get_market_provider)],
    rates: Annotated[object, Depends(get_rates_provider)],
):
    return market.refresh_all(session, provider, rates)


@router.get("/data-sources", response_model=list[DataSourceStatusOut])
def data_sources(session: SessionDep):
    return market.source_statuses(session)


def _asset_out(asset: Asset) -> AssetOut:
    return AssetOut(
        ticker=asset.ticker,
        name=asset.name,
        asset_class=AssetClass(asset.asset_class),
        class_confirmed=asset.class_confirmed,
        sector=asset.sector_override or asset.sector,
    )


@router.get("/assets/search", response_model=list[AssetOut])
def search_assets(session: SessionDep, q: str = "", limit: int = 10):
    """Autocomplete over known assets (the B3 instruments list is loaded in later phases)."""
    term = f"%{q.strip().upper()}%"
    query = select(Asset).where(or_(Asset.ticker.ilike(term), Asset.name.ilike(term))).order_by(Asset.ticker)
    return [_asset_out(a) for a in session.scalars(query.limit(limit)).all()]


@router.patch("/assets/{ticker}", response_model=AssetOut)
def patch_asset(ticker: str, payload: AssetPatch, session: SessionDep):
    asset = session.scalar(select(Asset).where(Asset.ticker == ticker.upper()))
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ativo não encontrado")
    if payload.name is not None:
        asset.name = payload.name
    if payload.asset_class is not None:
        asset.asset_class = payload.asset_class.value
        asset.class_confirmed = True
    if payload.sector_override is not None:
        asset.sector_override = payload.sector_override or None
    session.commit()
    return _asset_out(asset)
