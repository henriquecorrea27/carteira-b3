import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.corporate_events import get_events_source
from app.api.portfolio import get_market_provider
from app.core.db import SessionLocal, get_session
from app.fundamentals import service
from app.schemas.fundamentals import FundamentalsOut, IndicatorOut, IngestOut

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])
SessionDep = Annotated[Session, Depends(get_session)]
log = logging.getLogger(__name__)
_running = {"ingest": False}


def _run_ingest() -> None:
    try:
        with SessionLocal() as session:
            service.ingest(session)
    except Exception:
        log.exception("CVM ingestion failed")
    finally:
        _running["ingest"] = False


@router.post("/ingest", response_model=IngestOut, status_code=status.HTTP_202_ACCEPTED)
def ingest(background: BackgroundTasks):
    """Downloads and processes CVM data in the background (about a minute)."""
    if _running["ingest"]:
        return IngestOut(started=False, message="ingestão já em andamento")
    _running["ingest"] = True
    background.add_task(_run_ingest)
    return IngestOut(started=True, message="ingestão iniciada")


@router.get("/{ticker}", response_model=FundamentalsOut)
def fundamentals(
    ticker: str,
    session: SessionDep,
    market: Annotated[object, Depends(get_market_provider)],
    events: Annotated[object, Depends(get_events_source)],
):
    try:
        f = service.fundamentals_for(session, ticker, market, events)
    except service.UnknownTickerError as err:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "ticker não encontrado nos dados da CVM (só ações listadas; FIIs, ETFs e BDRs não têm análise)",
        ) from err
    r = f.result
    return FundamentalsOut(
        ticker=f.ticker,
        cnpj=f.cnpj,
        name=f.name,
        sector=f.sector,
        special_sector=r.special_sector,
        template=f.template,
        price=f.price,
        price_date=f.price_date,
        shares_outstanding=f.shares.outstanding if f.shares else None,
        shares_source=f.shares.source if f.shares else None,
        profitable_years=r.profitable_years,
        years_available=r.years_available,
        last_dfp=r.last_dfp,
        last_itr=r.last_itr,
        received_on=r.received_on,
        indicators=[IndicatorOut.model_validate(i) for i in r.indicators.values()],
        notes=r.notes,
    )
