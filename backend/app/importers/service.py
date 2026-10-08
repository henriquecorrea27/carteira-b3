"""Import pipeline: detect file → parse → dedupe → resolve ledger-dependent fields → validate → save.

`analyze` never writes; `commit` re-runs the analysis and saves the NEW rows (plus the possible
duplicates the user confirmed). Re-importing the same or an overlapping file is a no-op thanks to
the per-row dedup hash."""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.b3_movements import B3MovementsImporter
from app.importers.b3_trades import B3TradesImporter
from app.importers.base import Candidate, ImportRow, PortfolioImporter, RowStatus
from app.models import Asset, Transaction
from app.portfolio.engine import LedgerEntry, LedgerError, build_portfolio
from app.portfolio.service import ensure_asset, fill_row
from app.portfolio.types import TransactionSource, TransactionType
from app.schemas.transaction import TransactionIn

T = TransactionType
IMPORTERS: list[PortfolioImporter] = [B3TradesImporter(), B3MovementsImporter()]
_NEW_SEQ = 10**12


class UnknownFileError(ValueError):
    pass


@dataclass
class UploadedFile:
    name: str
    content: bytes


@dataclass
class Analysis:
    rows: list[ImportRow]
    files: dict[str, str]  # file name → importer name
    payloads: dict[int, TransactionIn]  # id(row) → resolved transaction


def _read_sheet(upload: UploadedFile) -> tuple[str, list[str], list[list]]:
    try:
        workbook = load_workbook(BytesIO(upload.content), read_only=True, data_only=True)
    except Exception as err:  # openpyxl raises many unrelated types for non-xlsx input
        raise UnknownFileError(f"{upload.name}: não é uma planilha .xlsx válida") from err
    sheet = workbook.worksheets[0]
    # B3 exports declare a bogus <dimension ref="A1"/>; without this, read-only mode yields one cell
    sheet.reset_dimensions()
    rows = [list(r) for r in sheet.iter_rows(values_only=True)]
    workbook.close()
    if not rows:
        raise UnknownFileError(f"{upload.name}: planilha vazia")
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    data = [r for r in rows[1:] if any(v not in (None, "") for v in r)]
    return sheet.title, header, data


def _parse_files(files: list[UploadedFile]) -> tuple[list[ImportRow], dict[str, str]]:
    rows: list[ImportRow] = []
    detected: dict[str, str] = {}
    for upload in files:
        title, header, data = _read_sheet(upload)
        importer = next((imp for imp in IMPORTERS if imp.matches(title, header)), None)
        if importer is None:
            raise UnknownFileError(
                f"{upload.name}: layout não reconhecido "
                "(esperado extrato de Negociação ou Movimentação da B3)"
            )
        detected[upload.name] = importer.name
        rows.extend(importer.parse(upload.name, data))
    return rows, detected


def _mark_duplicates(session: Session, rows: list[ImportRow]) -> None:
    stored = set(session.scalars(select(Transaction.dedup_hash).where(Transaction.dedup_hash.is_not(None))))
    seen: set[str] = set()
    manual = {
        (t.date, t.ticker, t.type, t.quantity)
        for t in session.scalars(
            select(Transaction).where(Transaction.source == TransactionSource.MANUAL.value)
        )
    }
    for row in rows:
        if row.status != RowStatus.NEW or row.dedup_hash is None:
            continue
        if row.dedup_hash in stored:
            row.status, row.reason = RowStatus.DUPLICATE, "já importado anteriormente"
        elif row.dedup_hash in seen:
            row.status, row.reason = RowStatus.DUPLICATE, "linha repetida em outro arquivo enviado"
        else:
            seen.add(row.dedup_hash)
            c = row.candidate
            if c and (c.date, c.ticker, c.type.value, c.quantity) in manual:
                row.status = RowStatus.POSSIBLE_DUPLICATE
                row.reason = "parecido com um lançamento manual (mesma data, ticker, tipo e quantidade)"


def _merge_split_events(rows: list[ImportRow]) -> None:
    """The same split/reverse split is credited once per broker; merge into a single event."""
    groups: dict[tuple, list[ImportRow]] = defaultdict(list)
    for row in rows:
        c = row.candidate
        if row.status == RowStatus.NEW and c and c.type in (T.SPLIT, T.REVERSE_SPLIT):
            groups[(c.date, c.ticker, c.type)].append(row)
    for group in groups.values():
        head, *rest = group
        head.candidate.credited_quantity = sum((r.candidate.credited_quantity for r in group), Decimal(0))
        head.candidate.broker = None
        for row in rest:
            row.status, row.reason = RowStatus.DUPLICATE, f"somado ao evento da linha {head.line}"
            head.merged_lines.append(row.line)


def _snap(factor: Decimal) -> Decimal:
    """Corporate-event factors are usually whole numbers; credited quantities lose fractions
    (sent to auction), so snap to the nearest integer when within 2%."""
    nearest = factor.to_integral_value()
    if nearest >= 1 and abs(factor - nearest) / nearest < Decimal("0.02"):
        return nearest
    return factor.quantize(Decimal("0.00000001"))


def _to_payload(c: Candidate) -> TransactionIn:
    return TransactionIn(
        date=c.date,
        ticker=c.ticker,
        type=c.type,
        quantity=c.quantity or None,
        price=c.price,
        factor=c.factor,
        gross_amount=c.gross_amount,
        tax_withheld=c.tax_withheld,
        payment_date=c.payment_date,
        status=c.status,
        broker=c.broker,
        notes=c.notes,
    )


def _entry(payload: TransactionIn, seq: int) -> LedgerEntry:
    return replace(
        fill_row(Transaction(source=TransactionSource.B3.value), payload).to_entry(), id=-seq, seq=seq
    )


def analyze(
    session: Session, files: list[UploadedFile], include_possible_duplicates: bool = False
) -> Analysis:
    rows, detected = _parse_files(files)
    _mark_duplicates(session, rows)
    _merge_split_events(rows)

    existing = [t.to_entry() for t in session.scalars(select(Transaction))]
    accepted = {RowStatus.NEW} | ({RowStatus.POSSIBLE_DUPLICATE} if include_possible_duplicates else set())
    candidates = [r for r in rows if r.status in accepted and r.candidate is not None]
    seq_of = {id(r): _NEW_SEQ + i for i, r in enumerate(candidates)}
    row_by_seq = {seq_of[id(r)]: r for r in candidates}
    payloads: dict[int, TransactionIn] = {}

    def fail(row: ImportRow, reason: str) -> None:
        row.status, row.reason = RowStatus.ERROR, reason
        payloads.pop(id(row), None)

    # Plain rows first; split events need the position on the day before, so they are resolved in date order
    for row in candidates:
        if row.candidate.type not in (T.SPLIT, T.REVERSE_SPLIT):
            try:
                payloads[id(row)] = _to_payload(row.candidate)
            except ValidationError as err:
                fail(row, "; ".join(e["msg"].removeprefix("Value error, ") for e in err.errors()))
    split_rows = sorted(
        (r for r in candidates if r.candidate.type in (T.SPLIT, T.REVERSE_SPLIT)),
        key=lambda r: r.candidate.date,
    )
    for row in split_rows:
        c = row.candidate
        entries = existing + [_entry(p, seq_of[rid]) for rid, p in payloads.items()]
        try:
            held = build_portfolio(entries, until=c.date - timedelta(days=1)).position(c.ticker).quantity
        except LedgerError as err:
            fail(row, f"não foi possível calcular a posição antes do evento: {err.message}")
            continue
        if held <= 0 or not c.credited_quantity:
            fail(row, f"{'desdobro' if c.type == T.SPLIT else 'grupamento'} sem posição na data")
            continue
        raw = (held + c.credited_quantity) / held if c.type == T.SPLIT else held / c.credited_quantity
        c.factor = _snap(raw)
        c.notes = f"fator calculado a partir da posição ({held.normalize()} ações) e da quantidade creditada"
        payloads[id(row)] = _to_payload(c)

    # Validate the whole ledger; drop failing rows one at a time so the rest can still be imported
    for _ in range(len(payloads) + 1):
        entries = existing + [_entry(p, seq_of[rid]) for rid, p in payloads.items()]
        try:
            build_portfolio(entries)
            break
        except LedgerError as err:
            row = row_by_seq.get(err.entry.seq)
            if row is None:
                # An existing transaction broke: blame the earliest new row of that ticker
                row = min(
                    (r for r in candidates if id(r) in payloads and r.candidate.ticker == err.entry.ticker),
                    key=lambda r: r.candidate.date,
                    default=None,
                )
                if row is None:
                    raise
            fail(row, err.message)

    return Analysis(rows=rows, files=detected, payloads=payloads)


def commit(
    session: Session, files: list[UploadedFile], include_possible_duplicates: bool = False
) -> Analysis:
    analysis = analyze(session, files, include_possible_duplicates)
    names: dict[str, str] = {}
    for row in analysis.rows:
        payload = analysis.payloads.get(id(row))
        if payload is None:
            continue
        tx = fill_row(Transaction(source=TransactionSource.B3.value, user_edited=False), payload)
        tx.dedup_hash = row.dedup_hash
        ensure_asset(session, tx.ticker)
        session.add(tx)
        if row.candidate.asset_name:
            names.setdefault(tx.ticker, row.candidate.asset_name)
    for asset in session.scalars(select(Asset).where(Asset.ticker.in_(names), Asset.name.is_(None))):
        asset.name = names[asset.ticker]
    session.commit()
    return analysis
