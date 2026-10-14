"""Watchlist: tickers alerted on Discord ONLY by the price against the SMA200 (CLAUDE.md §6.5)."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.portfolio import get_market_provider
from app.core.config import get_settings
from app.core.db import get_session
from app.models import PriceHistory, WatchlistItem
from app.notifications import service
from app.notifications.base import split_message
from app.notifications.discord import DiscordNotifier
from app.notifications.watchlist import WATCH_DAYS, WatchLine, limits, watch_lines
from app.portfolio.tickers import InvalidTickerError, normalize_ticker
from app.rules.service import sync_history
from app.schemas.watchlist import (
    DispatchOut,
    WatchItemIn,
    WatchItemOut,
    WatchItemPatch,
    WatchlistOut,
    WatchlistPreviewOut,
)

router = APIRouter(tags=["watchlist"])
SessionDep = Annotated[Session, Depends(get_session)]
MarketDep = Annotated[object, Depends(get_market_provider)]
WatchNotifierDep = Annotated[object, Depends(service.get_watchlist_notifier)]


def _round(value: Decimal | None, places: str) -> Decimal | None:
    return None if value is None else value.quantize(Decimal(places))


def _out(w: WatchLine) -> WatchItemOut:
    return WatchItemOut(
        **w.__dict__
        | {
            "price": _round(w.price, "0.01"),
            "sma": _round(w.sma, "0.0001"),
            "distance": _round(w.distance, "0.000001"),
        }
    )


def _item(session: Session, ticker: str) -> WatchlistItem:
    try:
        ticker = normalize_ticker(ticker)
    except InvalidTickerError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticker inválido") from err
    item = session.scalar(select(WatchlistItem).where(WatchlistItem.ticker == ticker))
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{ticker} não está na lista de observação")
    return item


def _line(session: Session, ticker: str) -> WatchItemOut:
    today = service.local_now().date()
    return _out(next(w for w in watch_lines(session, today) if w.ticker == ticker))


@router.get("/watchlist", response_model=WatchlistOut)
def get_watchlist(session: SessionDep, market: MarketDep):
    """Every ticker with its distance from the SMA (price history re-synced once a day per ticker)."""
    now = service.local_now()
    lim = limits()
    last = service.last_sent(session, kind=service.WATCHLIST)
    return WatchlistOut(
        items=[_out(w) for w in watch_lines(session, now.date(), market)],
        channel=service.watchlist_channel(),
        report_time=get_settings().report_time,
        sma_days=lim.sma_days,
        cheap=lim.cheap,
        expensive=lim.expensive,
        last_scheduled=last.report_date if last else None,
    )


@router.post("/watchlist", response_model=WatchItemOut, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(payload: WatchItemIn, session: SessionDep, market: MarketDep):
    try:
        ticker = normalize_ticker(payload.ticker)
    except InvalidTickerError as err:
        detail = f"Ticker inválido: {payload.ticker}"
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail) from err
    if session.scalar(select(WatchlistItem.id).where(WatchlistItem.ticker == ticker)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{ticker} já está na lista de observação.")
    sync_history(session, ticker, market, service.local_now().date(), days=WATCH_DAYS)
    if session.scalar(select(PriceHistory.id).where(PriceHistory.ticker == ticker).limit(1)) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Não encontramos cotações de {ticker} no Yahoo Finance. "
            "Confira o código (ou tente de novo mais tarde).",
        )
    note = (payload.note or "").strip() or None
    session.add(WatchlistItem(ticker=ticker, note=note))
    session.commit()
    return _line(session, ticker)


@router.patch("/watchlist/{ticker}", response_model=WatchItemOut)
def edit_watch_item(ticker: str, payload: WatchItemPatch, session: SessionDep):
    item = _item(session, ticker)
    item.note = (payload.note or "").strip() or None
    session.commit()
    return _line(session, item.ticker)


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(ticker: str, session: SessionDep):
    session.delete(_item(session, ticker))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/watchlist/preview", response_model=WatchlistPreviewOut)
def preview_watchlist(session: SessionDep):
    """The alert as it would be sent now (cached prices; GET /watchlist refreshes them)."""
    now = service.local_now()
    day = service.manual_day(now)
    _, content = service.compose_watchlist(session, day, now)
    return WatchlistPreviewOut(
        date=day,
        content=content,
        messages=split_message(content, DiscordNotifier.max_length),
        channel=service.watchlist_channel(),
    )


@router.post("/watchlist/send", response_model=DispatchOut)
def send_watchlist(session: SessionDep, notifier: WatchNotifierDep, market: MarketDep):
    """'Enviar agora': manual send (does not count as the scheduled alert of the day)."""
    if notifier is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Webhook do Discord não configurado: coloque a URL em DISCORD_WATCHLIST_WEBHOOK_URL (ou "
            "DISCORD_WEBHOOK_URL) no backend/.env e reinicie o backend.",
        )
    if not service.has_watchlist(session):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A lista de observação está vazia.")
    now = service.local_now()
    dispatch = service.send_watchlist(session, notifier, service.manual_day(now), now, service.MANUAL, market)
    if dispatch.status != service.SENT:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Aviso não enviado: {dispatch.error}")
    return dispatch


@router.get("/watchlist/dispatches", response_model=list[DispatchOut])
def watchlist_dispatches(session: SessionDep, limit: int = 10):
    return service.recent_dispatches(session, max(1, min(limit, 50)), kind=service.WATCHLIST)
