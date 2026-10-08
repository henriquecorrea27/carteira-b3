from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.corporate_events import service
from app.corporate_events.b3_source import B3CorporateEventsSource
from app.schemas.portfolio import AgendaItemOut, EventsSyncOut, PendingIssueOut

router = APIRouter(tags=["corporate-events"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_events_source():
    return B3CorporateEventsSource()


@router.post("/corporate-events/sync", response_model=EventsSyncOut)
def sync_events(session: SessionDep, source: Annotated[object, Depends(get_events_source)]):
    return service.sync(session, source)


@router.get("/provents/agenda", response_model=list[AgendaItemOut])
def provents_agenda(session: SessionDep):
    return service.agenda(session)


@router.get("/portfolio/pending", response_model=list[PendingIssueOut])
def portfolio_pending(session: SessionDep):
    return service.pending(session)
