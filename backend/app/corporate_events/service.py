"""Turns cached corporate events into ledger transactions (CLAUDE.md §3.9).

- Cash event: if the position at the end of the data-com is > 0, an AUTO provent is generated with
  quantity × value per share and the withholding in force on the payment date. ANNOUNCED until the
  payment date, then PAID; CONFIRMED rows come from the B3 Movimentação import.
- Stock event (split, reverse split, bonus): applied on the ex-date with the source's factor. Bonuses
  have no attributed cost in the source, so they stay "pending cost" until the user fills it.
- An event already present in the ledger (imported from B3 or typed by the user) is not generated
  again; imported rows are enriched with the event dates (data-com / ex-date).
- Manual edits win: AUTO rows edited by the user are never touched, and deleting an AUTO row dismisses
  its event for good.
- apply_events is idempotent and runs after every ledger change, so retroactive trades recalculate
  the provents they affect.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.parallel import fetch_all
from app.corporate_events.base import CorporateEventsSource
from app.market_data.service import record_status, tracked_tickers
from app.models import CorporateEvent, Transaction
from app.portfolio.engine import LedgerError, build_portfolio
from app.portfolio.service import ensure_asset
from app.portfolio.tax import default_tax_table
from app.portfolio.types import ProventStatus, TransactionSource, TransactionType

log = logging.getLogger(__name__)
T = TransactionType
ZERO = Decimal(0)
CENT = Decimal("0.01")
SOURCE_STATUS = "corporate_events"
# Imported rows are credited a few days after the data-com / payment date
_CASH_MATCH_DAYS = 5
_STOCK_MATCH_DAYS = 30
# Parallel requests to the B3 site (kept low: it is a public site, not an API)
_B3_WORKERS = 6


@dataclass
class ApplyResult:
    created: int = 0
    updated: int = 0
    removed: int = 0
    enriched: int = 0
    skipped: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    issuers: int = 0
    events_seen: int = 0
    errors: list[str] = field(default_factory=list)
    applied: ApplyResult = field(default_factory=ApplyResult)


def sync(session: Session, source: CorporateEventsSource, today: date | None = None) -> SyncResult:
    """Fetch events for every issuer the user holds or held, cache them and apply them to the ledger."""
    result = SyncResult()
    issuers = sorted({ticker[:4] for ticker in relevant_tickers(session, today or date.today())})
    now = datetime.now(UTC)
    fetched = fetch_all(source.events_for_issuer, issuers, workers=_B3_WORKERS)
    for issuer in issuers:
        events = fetched[issuer]
        if isinstance(events, Exception):
            log.warning("corporate events for %s failed: %s", issuer, events)
            result.errors.append(f"{issuer}: {events}")
            continue
        result.issuers += 1
        for ev in events:
            values = {k: v for k, v in ev.__dict__.items()}
            stmt = insert(CorporateEvent).values(
                **values, source=source.name, last_seen_at=now, dismissed=False
            )
            update = {k: stmt.excluded[k] for k in values if k != "event_key"} | {"last_seen_at": now}
            session.execute(stmt.on_conflict_do_update(index_elements=["event_key"], set_=update))
            result.events_seen += 1
    message = "; ".join(result.errors) if result.errors else None
    record_status(session, SOURCE_STATUS, not result.errors or result.issuers > 0, message)
    session.commit()
    result.applied = apply_events(session, today)
    return result


def relevant_tickers(session: Session, today: date) -> set[str]:
    """Tickers held now or traded in the last ~13 months. The source only lists cash events of the last
    12 months, so older closed positions (often delisted after mergers) have nothing new to fetch."""
    rows = list(session.scalars(select(Transaction)))
    held = {p.ticker for p in build_portfolio([r.to_entry() for r in rows]).open_positions}
    since = today - timedelta(days=400)
    return held | {r.ticker for r in rows if r.date >= since}


def _cash_matches(row: Transaction, ev: CorporateEvent) -> bool:
    if row.type != ev.tx_type or row.ticker != ev.ticker or row.price is None:
        return False
    tolerance = max(Decimal("0.0006"), ev.value * Decimal("0.01"))
    if abs(row.price - ev.value) > tolerance:
        return False
    paid = row.payment_date or row.date
    if ev.payment_date is not None:
        return ev.payment_date <= paid <= ev.payment_date + timedelta(days=_CASH_MATCH_DAYS)
    return row.date == ev.record_date


def _stock_matches(row: Transaction, ev: CorporateEvent) -> bool:
    return (
        row.type == ev.tx_type
        and row.ticker == ev.ticker
        and ev.record_date <= row.date <= ev.record_date + timedelta(days=_STOCK_MATCH_DAYS)
    )


def _families(rows: Sequence[Transaction]) -> dict[str, frozenset[str]]:
    """Tickers linked by ticker changes (incorporations): a position only depends on the rows of its family,
    so a replay of the family gives the same quantities as a replay of the whole ledger."""
    parent: dict[str, str] = {}

    def root(t: str) -> str:
        while parent.setdefault(t, t) != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    for r in rows:
        root(r.ticker)
        if r.target_ticker:
            parent[root(r.ticker)] = root(r.target_ticker)
    groups: dict[str, set[str]] = {}
    for t in parent:
        groups.setdefault(root(t), set()).add(t)
    return {t: frozenset(groups[root(t)]) for t in parent}


def _replays(rows: Sequence[Transaction]) -> bool:
    try:
        build_portfolio([r.to_entry() for r in rows])
        return True
    except LedgerError:
        return False


def _fill_auto(tx: Transaction, ev: CorporateEvent, held: Decimal, today: date) -> None:
    tx.ticker = ev.ticker
    tx.type = ev.tx_type
    tx.source = TransactionSource.AUTO.value
    tx.dedup_hash = ev.event_key
    tx.broker = None
    tx.costs = ZERO
    if ev.category == "CASH":
        tx.date = ev.record_date
        tx.quantity = held
        tx.price = ev.value
        gross = (held * ev.value).quantize(CENT, rounding=ROUND_DOWN)
        tax_date = ev.payment_date or ev.record_date
        tax = default_tax_table().withheld(T(ev.tx_type), tax_date, gross)
        tx.gross_amount, tx.tax_withheld, tx.net_amount = gross, tax, gross - tax
        tx.payment_date = ev.payment_date
        paid = ev.payment_date is not None and ev.payment_date <= today
        tx.status = (ProventStatus.PAID if paid else ProventStatus.ANNOUNCED).value
        tx.notes = f"{ev.label.title()} {ev.related_to or ''}".strip()
    else:
        tx.date = ev.ex_date
        tx.price = None
        tx.gross_amount = tx.tax_withheld = tx.net_amount = None
        tx.payment_date = None
        tx.status = None
        if ev.tx_type == T.BONUS:
            tx.quantity = held * ev.factor
            tx.factor = None
            tx.notes = (
                f"Bonificação de {ev.value.normalize()}% — custo atribuído pendente; "
                "a fração não inteira vai a leilão"
            )
        else:
            tx.quantity = ZERO
            tx.factor = ev.factor
            tx.notes = f"{ev.label.title()} (fator {ev.factor.normalize()})"


def apply_events(session: Session, today: date | None = None) -> ApplyResult:
    today = today or date.today()
    result = ApplyResult()
    tracked = tracked_tickers(session)
    events = [
        ev
        for ev in session.scalars(select(CorporateEvent).where(CorporateEvent.tx_type.is_not(None)))
        if ev.ticker in tracked and ev.record_date >= tracked[ev.ticker] - timedelta(days=1)
    ]
    # Stock events first on the same day: they change the quantity provents are computed on
    events.sort(key=lambda ev: (ev.ex_date, ev.category != "STOCK", ev.record_date))
    rows = list(session.scalars(select(Transaction)))
    families = _families(rows)
    auto_by_key = {r.dedup_hash: r for r in rows if r.source == TransactionSource.AUTO.value and r.dedup_hash}
    used: set[int] = set()

    for ev in events:
        current = auto_by_key.get(ev.event_key)
        if current is not None and current.user_edited:
            continue
        # Position at the end of the data-com is only known after it; until then it is agenda-only
        if ev.dismissed or ev.record_date >= today:
            continue
        family = families.get(ev.ticker, frozenset({ev.ticker}))
        others = [r for r in rows if r is not current and r.ticker in family]
        try:
            held = (
                build_portfolio([r.to_entry() for r in others], until=ev.record_date)
                .position(ev.ticker)
                .quantity
            )
        except LedgerError as err:
            result.skipped.append(f"{ev.ticker} {ev.label} {ev.record_date:%d/%m/%Y}: {err.message}")
            continue

        def drop_current() -> None:
            nonlocal current
            if current is not None:
                rows.remove(current)
                session.delete(current)
                result.removed += 1
                current = None

        if held <= 0:
            drop_current()
            continue

        matcher = _cash_matches if ev.category == "CASH" else _stock_matches
        existing = [
            r
            for r in others
            if r.id not in used and r.source != TransactionSource.AUTO.value and matcher(r, ev)
        ]
        if existing:
            drop_current()
            for r in existing:
                used.add(r.id)
                target = ev.record_date if ev.category == "CASH" else ev.ex_date
                if r.source == TransactionSource.B3.value and not r.user_edited and r.date != target:
                    previous = r.date
                    r.date = target
                    if ev.category == "STOCK" and not _replays([r for r in rows if r.ticker in family]):
                        r.date = previous
                    else:
                        result.enriched += 1
            continue

        tx = current or Transaction(user_edited=False)
        snapshot = None if current is None else {c: getattr(tx, c) for c in ("date", "quantity", "factor")}
        _fill_auto(tx, ev, held, today)
        if current is None:
            rows.append(tx)
        if ev.category == "STOCK" and not _replays([r for r in rows if r.ticker in family]):
            result.skipped.append(f"{ev.ticker} {ev.label} {ev.record_date:%d/%m/%Y}: quebraria o livro")
            if current is None:
                rows.remove(tx)
            else:
                for col, value in snapshot.items():
                    setattr(tx, col, value)
            continue
        if current is None:
            ensure_asset(session, ev.ticker)
            session.add(tx)
            auto_by_key[ev.event_key] = tx
            result.created += 1
        elif session.is_modified(tx):
            result.updated += 1

    session.commit()
    return result


@dataclass
class AgendaItem:
    ticker: str
    kind: str  # DIVIDEND | JCP | INCOME | SPLIT | REVERSE_SPLIT | BONUS
    label: str
    record_date: date
    ex_date: date
    payment_date: date | None
    value: Decimal
    factor: Decimal | None
    quantity: Decimal  # held at the data-com, or held today when the data-com is still ahead
    estimated_net: Decimal | None
    in_ledger: bool


def agenda(session: Session, today: date | None = None) -> list[AgendaItem]:
    """Upcoming data-com dates and payments for the tickers currently held."""
    today = today or date.today()
    rows = list(session.scalars(select(Transaction)))
    entries = [r.to_entry() for r in rows]
    current = build_portfolio(entries)
    keys = {r.dedup_hash for r in rows if r.dedup_hash}
    items = []
    for ev in session.scalars(select(CorporateEvent).where(CorporateEvent.tx_type.is_not(None))):
        upcoming = ev.record_date >= today or (ev.payment_date is not None and ev.payment_date >= today)
        if not upcoming or ev.dismissed or ev.ticker is None:
            continue
        if ev.record_date >= today:
            held = current.position(ev.ticker).quantity
        else:
            held = build_portfolio(entries, until=ev.record_date).position(ev.ticker).quantity
        if held <= 0:
            continue
        net = None
        if ev.category == "CASH":
            gross = (held * ev.value).quantize(CENT, rounding=ROUND_DOWN)
            net = gross - default_tax_table().withheld(
                T(ev.tx_type), ev.payment_date or ev.record_date, gross
            )
        items.append(
            AgendaItem(
                ticker=ev.ticker,
                kind=ev.tx_type,
                label=ev.label,
                record_date=ev.record_date,
                ex_date=ev.ex_date,
                payment_date=ev.payment_date,
                value=ev.value,
                factor=ev.factor,
                quantity=held,
                estimated_net=net,
                in_ledger=ev.event_key in keys,
            )
        )
    return sorted(items, key=lambda i: (i.payment_date or i.record_date, i.ticker))


@dataclass
class PendingIssue:
    id: str
    kind: str  # BONUS_NO_COST | UNRECOGNIZED_EVENT
    ticker: str
    date: date
    message: str
    transaction_id: int | None


def pending(session: Session, today: date | None = None) -> list[PendingIssue]:
    today = today or date.today()
    out: list[PendingIssue] = []
    rows = list(session.scalars(select(Transaction)))
    for r in rows:
        if r.type == T.BONUS and r.price is None:
            qty = format(r.quantity.normalize(), "f").replace(".", ",")
            out.append(
                PendingIssue(
                    id=f"bonus-{r.id}",
                    kind="BONUS_NO_COST",
                    ticker=r.ticker,
                    date=r.date,
                    message=f"Bonificação de {qty} ações sem custo atribuído — "
                    "informe o valor do aviso aos acionistas.",
                    transaction_id=r.id,
                )
            )
    held = {p.ticker for p in build_portfolio([r.to_entry() for r in rows]).open_positions}
    recent = today - timedelta(days=90)
    unknown = select(CorporateEvent).where(
        CorporateEvent.tx_type.is_(None), CorporateEvent.record_date >= recent
    )
    for ev in session.scalars(unknown):
        if ev.ticker in held and not ev.dismissed:
            out.append(
                PendingIssue(
                    id=f"event-{ev.id}",
                    kind="UNRECOGNIZED_EVENT",
                    ticker=ev.ticker,
                    date=ev.record_date,
                    message=f"Evento '{ev.label.title()}' ({ev.value.normalize()}) não é tratado "
                    "automaticamente — lance manualmente se afetar a sua posição.",
                    transaction_id=None,
                )
            )
    return sorted(out, key=lambda p: p.date, reverse=True)
