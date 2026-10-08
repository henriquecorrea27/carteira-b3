from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.corporate_events import get_events_source
from app.api.portfolio import get_market_provider
from app.core.db import get_session
from app.fundamentals.service import UnknownTickerError
from app.portfolio.tickers import InvalidTickerError, normalize_ticker
from app.rules import service
from app.schemas.analysis import AnalysisOut, PortfolioRunOut, PriceBarOut, analysis_out

router = APIRouter(tags=["analysis"])
SessionDep = Annotated[Session, Depends(get_session)]
MarketDep = Annotated[object, Depends(get_market_provider)]
EventsDep = Annotated[object, Depends(get_events_source)]


@router.get("/analysis/{ticker}", response_model=AnalysisOut)
def analysis(ticker: str, session: SessionDep, market: MarketDep, events: EventsDep):
    try:
        return analysis_out(service.analyze(session, ticker, market, events))
    except UnknownTickerError as err:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Não encontramos {ticker.upper()} entre as ações listadas na CVM "
            "(FIIs, ETFs e BDRs não têm análise por regras).",
        ) from err


@router.post("/analysis/portfolio", response_model=PortfolioRunOut)
def analyze_portfolio(session: SessionDep, market: MarketDep, events: EventsDep):
    """Re-evaluates every stock in the portfolio and stores today's snapshots."""
    return service.analyze_portfolio(session, market, events)


@router.get("/prices/{ticker}", response_model=list[PriceBarOut])
def prices(ticker: str, session: SessionDep, market: MarketDep, days: int = service.CHART_DAYS):
    try:
        ticker = normalize_ticker(ticker)
    except InvalidTickerError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticker inválido") from err
    bars = service.price_bars(session, ticker, market, days=max(30, min(days, 3650)))
    return [
        PriceBarOut(date=b.date, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)
        for b in bars
    ]
