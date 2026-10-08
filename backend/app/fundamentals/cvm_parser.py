"""Reads a CVM DFP/ITR yearly zip into per-company figures.

Real layout (validated on dados.cvm.gov.br, Oct/2026):
- `{doc}_cia_aberta_{year}.csv` index: CNPJ_CIA, DT_REFER, VERSAO, DT_RECEB … (one row per version).
- `{doc}_cia_aberta_{BPA|BPP|DRE|DFC_MI|DFC_MD}_{con|ind}_{year}.csv`: CNPJ_CIA, DT_REFER, VERSAO,
  ESCALA_MOEDA (MIL | UNIDADE), ORDEM_EXERC (ÚLTIMO | PENÚLTIMO), DT_INI_EXERC (flows only), DT_FIM_EXERC,
  CD_CONTA, DS_CONTA, VL_CONTA. `;`-separated, latin-1.
- ITR income statements carry both the quarter and the year-to-date; cash flows only year-to-date. The
  PENÚLTIMO column of an ITR holds the same year-to-date of the previous year.
- `composicao_capital`: share counts WITHOUT a scale column — some companies report units, others
  thousands — so they are only a fallback (see app.fundamentals.shares).
"""

import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from app.fundamentals.extract import Account, Figures, Statement, dividends_paid, extract

LAST, PREVIOUS = "ÚLTIMO", "PENÚLTIMO"
_COLS = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "ESCALA_MOEDA",
    "ORDEM_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
]
_FLOW_STATEMENTS = ("DRE", "DFC_MI", "DFC_MD")
_STATEMENTS = ("BPA", "BPP", *_FLOW_STATEMENTS)


@dataclass
class ParsedPeriod:
    cnpj: str
    name: str
    doc_type: str  # DFP | ITR
    period_start: date | None
    period_end: date
    version: int
    received_on: date | None
    consolidated: bool
    comparative: bool
    figures: Figures


@dataclass
class CapitalComposition:
    cnpj: str
    as_of: date
    on: Decimal
    pn: Decimal
    treasury_on: Decimal
    treasury_pn: Decimal


def _read(zf: zipfile.ZipFile, member: str, usecols: list[str] | None = None) -> pd.DataFrame | None:
    if member not in zf.namelist():
        return None
    with zf.open(member) as fh:
        return pd.read_csv(fh, sep=";", encoding="latin1", dtype=str, usecols=usecols)


def _latest_versions(index: pd.DataFrame) -> pd.DataFrame:
    index = index.assign(VERSAO_N=index["VERSAO"].astype(int))
    return index.sort_values("VERSAO_N").groupby(["CNPJ_CIA", "DT_REFER"], as_index=False).last()


def _scaled(df: pd.DataFrame) -> list[Decimal]:
    """Values in R$ units. Earnings per share (3.99.*) are already in R$/share and never scaled."""
    factor = df["ESCALA_MOEDA"].map({"MIL": 1000}).fillna(1)
    per_share = df["CD_CONTA"].str.startswith("3.99")
    return [
        Decimal(v) * (1 if eps else int(f))
        for v, f, eps in zip(df["VL_CONTA"], factor, per_share, strict=True)
    ]


def _statement(rows: pd.DataFrame) -> Statement:
    return Statement(
        [Account(c, d, v) for c, d, v in zip(rows["CD_CONTA"], rows["DS_CONTA"], rows["VALUE"], strict=True)]
    )


def _pick_column(rows: pd.DataFrame, order: str) -> pd.DataFrame:
    """Rows of one period column; for flows, the year-to-date (earliest start) and not the quarter."""
    rows = rows[rows["ORDEM_EXERC"] == order]
    if "DT_INI_EXERC" in rows and len(rows):
        rows = rows[rows["DT_INI_EXERC"] == rows["DT_INI_EXERC"].min()]
    return rows


def parse_document(path: Path, doc_type: str) -> Iterator[ParsedPeriod]:
    """Yields the latest version of every company/period in one yearly zip (consolidated when the
    company publishes it, individual otherwise). ITR files also yield the prior-year comparatives."""
    prefix = doc_type.lower()
    year = path.stem.rsplit("_", 1)[-1]
    with zipfile.ZipFile(path) as zf:
        index = _read(zf, f"{prefix}_cia_aberta_{year}.csv")
        latest = _latest_versions(index)
        meta = {
            (r.CNPJ_CIA, r.DT_REFER): (int(r.VERSAO), r.DT_RECEB, r.DENOM_CIA) for r in latest.itertuples()
        }
        versions = latest[["CNPJ_CIA", "DT_REFER", "VERSAO"]]
        # (scope, statement) → {(cnpj, dt_refer): rows of the latest version}
        frames: dict[tuple[str, str], dict[tuple[str, str], pd.DataFrame]] = {}
        for scope in ("con", "ind"):
            for st in _STATEMENTS:
                cols = _COLS + (["DT_INI_EXERC"] if st in _FLOW_STATEMENTS else [])
                df = _read(zf, f"{prefix}_cia_aberta_{st}_{scope}_{year}.csv", usecols=cols)
                if df is None:
                    continue
                df = df.merge(versions, on=["CNPJ_CIA", "DT_REFER", "VERSAO"], how="inner")
                df = df.assign(VALUE=_scaled(df))
                frames[(scope, st)] = {key: rows for key, rows in df.groupby(["CNPJ_CIA", "DT_REFER"])}

    for (cnpj, refer), (version, received, name) in meta.items():
        scope = "con" if _has(frames, ("con", "DRE"), cnpj, refer) else "ind"
        parts = {st: _company_rows(frames.get((scope, st)), cnpj, refer) for st in _STATEMENTS}
        if parts["DRE"] is None or parts["BPA"] is None or parts["BPP"] is None:
            continue
        dfc = parts["DFC_MI"] if parts["DFC_MI"] is not None and len(parts["DFC_MI"]) else parts["DFC_MD"]
        parent_dfc = None
        if scope == "con":
            ind_mi = _company_rows(frames.get(("ind", "DFC_MI")), cnpj, refer)
            parent_dfc = (
                ind_mi if ind_mi is not None else _company_rows(frames.get(("ind", "DFC_MD")), cnpj, refer)
            )
        orders = [(LAST, False)] + ([(PREVIOUS, True)] if doc_type == "ITR" else [])
        template = None
        for order, comparative in orders:
            dre = _pick_column(parts["DRE"], order)
            if dre.empty:
                continue
            if comparative:
                # Prior-year year-to-date: only the flows are meaningful (balances are last year-end)
                bpa = bpp = Statement([])
            else:
                bpa = _statement(parts["BPA"][parts["BPA"]["ORDEM_EXERC"] == LAST])
                bpp = _statement(parts["BPP"][parts["BPP"]["ORDEM_EXERC"] == LAST])
            cash_flow = _statement(_pick_column(dfc, order)) if dfc is not None and len(dfc) else None
            if comparative:
                figures = _flows_only(dre, cash_flow, template or "INDUSTRIAL")
            else:
                figures = extract(bpa, bpp, _statement(dre), cash_flow)
                template = figures.template
            if parent_dfc is not None:
                parent_column = _pick_column(parent_dfc, order)
                if len(parent_column):
                    figures.dividends_paid = dividends_paid(_statement(parent_column))
            yield ParsedPeriod(
                cnpj=cnpj,
                name=name,
                doc_type=doc_type,
                period_start=date.fromisoformat(dre["DT_INI_EXERC"].iloc[0]),
                period_end=date.fromisoformat(dre["DT_FIM_EXERC"].iloc[0]),
                version=version,
                received_on=date.fromisoformat(received) if isinstance(received, str) else None,
                consolidated=scope == "con",
                comparative=comparative,
                figures=figures,
            )


def _flows_only(dre: pd.DataFrame, cash_flow: Statement | None, template: str) -> Figures:
    """Prior-year year-to-date column: income statement and cash flow only."""
    figures = extract(Statement([]), Statement([]), _statement(dre), cash_flow)
    figures.template = template
    figures.current_assets = figures.current_liabilities = figures.cash = None
    keep = {"lucro líquido", "fluxo de caixa"} | (
        {"depreciação e amortização"} if template == "INDUSTRIAL" else set()
    )
    figures.missing = [m for m in figures.missing if m in keep]
    return figures


def _has(frames, key, cnpj, refer) -> bool:
    return (cnpj, refer) in frames.get(key, {})


def _company_rows(groups: dict | None, cnpj: str, refer: str) -> pd.DataFrame | None:
    return None if groups is None else groups.get((cnpj, refer))


def parse_capital(path: Path, doc_type: str) -> list[CapitalComposition]:
    prefix = doc_type.lower()
    year = path.stem.rsplit("_", 1)[-1]
    with zipfile.ZipFile(path) as zf:
        df = _read(zf, f"{prefix}_cia_aberta_composicao_capital_{year}.csv")
    if df is None:
        return []
    df = df.assign(VERSAO_N=df["VERSAO"].astype(int)).sort_values(["DT_REFER", "VERSAO_N"])
    df = df.groupby("CNPJ_CIA", as_index=False).last()
    return [
        CapitalComposition(
            cnpj=r.CNPJ_CIA,
            as_of=date.fromisoformat(r.DT_REFER),
            on=Decimal(r.QT_ACAO_ORDIN_CAP_INTEGR or 0),
            pn=Decimal(r.QT_ACAO_PREF_CAP_INTEGR or 0),
            treasury_on=Decimal(r.QT_ACAO_ORDIN_TESOURO or 0),
            treasury_pn=Decimal(r.QT_ACAO_PREF_TESOURO or 0),
        )
        for r in df.itertuples()
    ]
