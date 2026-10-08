"""Database-facing portfolio operations. Every write replays the whole ledger through the engine
before committing, so the stored ledger is always consistent (no oversells, no orphan events)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Transaction
from app.portfolio.engine import LedgerEntry, LedgerError, PortfolioResult, build_portfolio
from app.portfolio.tax import default_tax_table
from app.portfolio.tickers import infer_asset_class
from app.portfolio.types import (
    PROVENT_TYPES,
    ProventStatus,
    TransactionSource,
    TransactionType,
)
from app.schemas.transaction import LedgerIssue, TransactionIn

ZERO = Decimal(0)
# New (unsaved) rows replay after existing rows of the same day and type
_NEW_ROW_SEQ = 10**12


class LedgerValidationError(Exception):
    def __init__(self, issues: list[LedgerIssue]):
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues


class TransactionNotFoundError(Exception):
    pass


def ensure_asset(session: Session, ticker: str) -> Asset:
    asset = session.scalar(select(Asset).where(Asset.ticker == ticker))
    if asset is None:
        asset = Asset(ticker=ticker, asset_class=infer_asset_class(ticker).value)
        session.add(asset)
        session.flush()
    return asset


def fill_row(row: Transaction, payload: TransactionIn) -> Transaction:
    row.date = payload.date
    row.ticker = payload.ticker
    row.type = payload.type.value
    row.quantity = payload.quantity or ZERO
    row.price = payload.price
    row.costs = payload.costs
    row.factor = payload.factor
    row.target_ticker = payload.target_ticker
    row.broker = payload.broker
    row.notes = payload.notes
    row.gross_amount = row.tax_withheld = row.net_amount = None
    row.payment_date = None
    row.status = None
    if payload.type in PROVENT_TYPES:
        payment_date = payload.payment_date or payload.date
        gross = (
            payload.gross_amount if payload.gross_amount is not None else row.quantity * (row.price or ZERO)
        )
        tax = (
            payload.tax_withheld
            if payload.tax_withheld is not None
            else default_tax_table().withheld(payload.type, payment_date, gross)
        )
        row.gross_amount = gross
        row.tax_withheld = tax
        row.net_amount = gross - tax
        row.payment_date = payment_date
        status = payload.status or (
            ProventStatus.PAID if payment_date <= date.today() else ProventStatus.ANNOUNCED
        )
        row.status = status.value
    return row


def _replay(entries: list[LedgerEntry]) -> PortfolioResult:
    try:
        return build_portfolio(entries)
    except LedgerError as err:
        entry_id = err.entry.id
        if entry_id is not None and entry_id < 0:
            issue = LedgerIssue(code=err.code, message=err.message, row=-entry_id - 1)
        else:
            issue = LedgerIssue(code=err.code, message=err.message, transaction_id=entry_id)
        raise LedgerValidationError([issue]) from err


def _all_rows(session: Session) -> Sequence[Transaction]:
    return session.scalars(select(Transaction).order_by(Transaction.date, Transaction.id)).all()


def _pending_entry(row: Transaction, index: int) -> LedgerEntry:
    entry = row.to_entry()
    return replace(entry, id=-(index + 1), seq=_NEW_ROW_SEQ + index)


def create_transactions(
    session: Session, payloads: Sequence[TransactionIn], source: TransactionSource = TransactionSource.MANUAL
) -> list[Transaction]:
    """All-or-nothing insert: if any row breaks the ledger, nothing is saved."""
    new_rows = [fill_row(Transaction(source=source.value, user_edited=False), p) for p in payloads]
    existing = [row.to_entry() for row in _all_rows(session)]
    _replay(existing + [_pending_entry(row, i) for i, row in enumerate(new_rows)])

    for row in new_rows:
        ensure_asset(session, row.ticker)
        if row.target_ticker:
            ensure_asset(session, row.target_ticker)
    session.add_all(new_rows)
    session.commit()
    return new_rows


def update_transaction(session: Session, transaction_id: int, payload: TransactionIn) -> Transaction:
    row = session.get(Transaction, transaction_id)
    if row is None:
        raise TransactionNotFoundError(transaction_id)
    others = [r.to_entry() for r in _all_rows(session) if r.id != transaction_id]
    candidate = fill_row(Transaction(source=row.source), payload)
    candidate_entry = replace(candidate.to_entry(), id=transaction_id, seq=transaction_id)
    _replay([*others, candidate_entry])

    fill_row(row, payload)
    row.user_edited = True
    ensure_asset(session, row.ticker)
    if row.target_ticker:
        ensure_asset(session, row.target_ticker)
    session.commit()
    return row


def delete_transaction(session: Session, transaction_id: int) -> None:
    row = session.get(Transaction, transaction_id)
    if row is None:
        raise TransactionNotFoundError(transaction_id)
    _replay([r.to_entry() for r in _all_rows(session) if r.id != transaction_id])
    session.delete(row)
    session.commit()


def list_transactions(
    session: Session,
    ticker: str | None = None,
    types: Sequence[TransactionType] | None = None,
    source: TransactionSource | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Sequence[Transaction]:
    query = select(Transaction)
    if ticker:
        query = query.where(Transaction.ticker == ticker)
    if types:
        query = query.where(Transaction.type.in_([t.value for t in types]))
    if source:
        query = query.where(Transaction.source == source.value)
    if date_from:
        query = query.where(Transaction.date >= date_from)
    if date_to:
        query = query.where(Transaction.date <= date_to)
    return session.scalars(query.order_by(Transaction.date.desc(), Transaction.id.desc())).all()


def current_portfolio(session: Session) -> PortfolioResult:
    return _replay([row.to_entry() for row in _all_rows(session)])
