from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.models import Asset
from app.portfolio import service
from app.portfolio.types import AssetClass
from app.schemas.portfolio import AssetOut, AssetPatch, PortfolioSummaryOut, PositionOut

router = APIRouter(tags=["portfolio"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/portfolio/positions", response_model=list[PositionOut])
def positions(session: SessionDep, include_closed: bool = False):
    return service.get_positions(session, include_closed)


@router.get("/portfolio/summary", response_model=PortfolioSummaryOut)
def summary(session: SessionDep):
    return service.get_summary(session)


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
