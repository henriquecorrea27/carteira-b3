from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.portfolio import service
from app.portfolio.tickers import InvalidTickerError, normalize_ticker
from app.portfolio.types import TransactionSource, TransactionType
from app.schemas.transaction import TransactionBatchIn, TransactionIn, TransactionOut

router = APIRouter(prefix="/transactions", tags=["transactions"])
SessionDep = Annotated[Session, Depends(get_session)]


def _ledger_error(err: service.LedgerValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[issue.model_dump() for issue in err.issues],
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    session: SessionDep,
    ticker: str | None = None,
    type: Annotated[list[TransactionType] | None, Query()] = None,
    source: TransactionSource | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    if ticker:
        try:
            ticker = normalize_ticker(ticker)
        except InvalidTickerError:
            return []
    return service.list_transactions(session, ticker, type, source, date_from, date_to)


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionIn, session: SessionDep):
    try:
        return service.create_transactions(session, [payload])[0]
    except service.LedgerValidationError as err:
        raise _ledger_error(err) from err


@router.post("/batch", response_model=list[TransactionOut], status_code=status.HTTP_201_CREATED)
def create_batch(payload: TransactionBatchIn, session: SessionDep):
    try:
        return service.create_transactions(session, payload.items)
    except service.LedgerValidationError as err:
        raise _ledger_error(err) from err


@router.put("/{transaction_id}", response_model=TransactionOut)
def update_transaction(transaction_id: int, payload: TransactionIn, session: SessionDep):
    try:
        return service.update_transaction(session, transaction_id, payload)
    except service.TransactionNotFoundError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lançamento não encontrado") from err
    except service.LedgerValidationError as err:
        raise _ledger_error(err) from err


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, session: SessionDep):
    try:
        service.delete_transaction(session, transaction_id)
    except service.TransactionNotFoundError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lançamento não encontrado") from err
    except service.LedgerValidationError as err:
        raise _ledger_error(err) from err
