from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.corporate_events.service import apply_events
from app.importers import service
from app.importers.base import RowStatus
from app.schemas.imports import ImportReportOut, ImportRowOut

router = APIRouter(prefix="/import", tags=["import"])
SessionDep = Annotated[Session, Depends(get_session)]
MAX_FILE_BYTES = 10 * 1024 * 1024


async def _read(files: list[UploadFile]) -> list[service.UploadedFile]:
    out = []
    for f in files:
        content = await f.read()
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"{f.filename}: arquivo maior que 10 MB")
        out.append(service.UploadedFile(name=f.filename or "arquivo.xlsx", content=content))
    return out


def _report(analysis: service.Analysis, committed: bool) -> ImportReportOut:
    rows = []
    for row in analysis.rows:
        out = ImportRowOut(
            file=row.file,
            line=row.line,
            status=row.status,
            reason=row.reason,
            raw=row.raw,
            merged_lines=row.merged_lines,
        )
        c = row.candidate
        if c is not None and row.status not in (RowStatus.DUPLICATE, RowStatus.IGNORED):
            out = out.model_copy(
                update={
                    "date": c.date,
                    "ticker": c.ticker,
                    "type": c.type,
                    "quantity": c.quantity
                    if c.type not in ("SPLIT", "REVERSE_SPLIT")
                    else c.credited_quantity,
                    "price": c.price,
                    "factor": c.factor,
                    "gross_amount": c.gross_amount,
                    "tax_withheld": c.tax_withheld,
                    "broker": c.broker,
                }
            )
        rows.append(out)
    return ImportReportOut(
        committed=committed,
        files=analysis.files,
        counts=Counter(row.status for row in analysis.rows),
        inserted=len(analysis.payloads) if committed else 0,
        rows=rows,
    )


@router.post("/b3/preview", response_model=ImportReportOut)
async def preview(
    session: SessionDep,
    files: Annotated[list[UploadFile], File()],
    include_possible_duplicates: bool = False,
):
    try:
        analysis = service.analyze(session, await _read(files), include_possible_duplicates)
    except service.UnknownFileError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
    return _report(analysis, committed=False)


@router.post("/b3/commit", response_model=ImportReportOut)
async def commit(
    session: SessionDep,
    files: Annotated[list[UploadFile], File()],
    include_possible_duplicates: bool = False,
):
    try:
        analysis = service.commit(session, await _read(files), include_possible_duplicates)
        apply_events(session)
    except service.UnknownFileError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
    return _report(analysis, committed=True)
