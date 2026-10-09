from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.notifications import service
from app.notifications.base import split_message
from app.notifications.discord import DiscordNotifier
from app.schemas.report import DispatchOut, ReportPreviewOut

router = APIRouter(tags=["report"])
SessionDep = Annotated[Session, Depends(get_session)]
NotifierDep = Annotated[object, Depends(service.get_notifier)]


@router.get("/report/preview", response_model=ReportPreviewOut)
def preview(session: SessionDep, notifier: NotifierDep):
    """The report as it would be sent now (uses the cached data; "Atualizar preços" refreshes it)."""
    now = service.local_now()
    day = service.manual_day(now)
    _, content = service.compose(session, day, now)
    last = service.last_sent(session)
    return ReportPreviewOut(
        date=day,
        content=content,
        messages=split_message(content, DiscordNotifier.max_length),
        configured=notifier is not None,
        report_time=get_settings().report_time,
        last_scheduled=last.report_date if last else None,
    )


@router.post("/report/send", response_model=DispatchOut)
def send(session: SessionDep, notifier: NotifierDep):
    """'Enviar relatório agora': manual send (does not count as the scheduled report of the day)."""
    if notifier is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Webhook do Discord não configurado: coloque a URL em DISCORD_WEBHOOK_URL no backend/.env "
            "e reinicie o backend.",
        )
    now = service.local_now()
    dispatch = service.send_report(session, notifier, service.manual_day(now), now, service.MANUAL)
    if dispatch.status != service.SENT:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Relatório não enviado: {dispatch.error}")
    return dispatch


@router.get("/report/dispatches", response_model=list[DispatchOut])
def dispatches(session: SessionDep, limit: int = 10):
    return service.recent_dispatches(session, max(1, min(limit, 50)))
