"""CVM ingestion (companies, tickers, extracted periods) and on-demand indicators for one ticker."""

import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.corporate_events.base import CorporateEventsError
from app.fundamentals import cvm_files
from app.fundamentals.cvm_parser import CapitalComposition, ParsedPeriod, parse_capital, parse_document
from app.fundamentals.indicators import FundamentalsResult, compute
from app.fundamentals.shares import ShareCount, from_b3, from_cvm
from app.market_data.base import MarketDataError, MarketDataProvider
from app.market_data.service import REVISE, record_status, store_bars
from app.models import Asset, Company, CompanyTicker, FundamentalPeriod, PriceHistory
from app.portfolio.tickers import InvalidTickerError, normalize_ticker
from app.portfolio.types import AssetClass
from app.rules.engine import classify_sector

log = logging.getLogger(__name__)
SOURCE_STATUS = "cvm"
_FIGURE_COLUMNS = (
    "revenue", "ebit", "net_income", "net_income_controlling", "d_and_a", "dividends_paid",
    "operating_cash_flow", "capex",
    "total_assets", "current_assets", "current_liabilities", "cash", "gross_debt", "leases",
    "equity", "equity_controlling", "eps",
)  # fmt: skip
_SHARE_CLASSES = {"Ações Ordinárias": "ON", "Ações Preferenciais": "PN", "Units": "UNIT"}
LIQUIDITY_DAYS = 61
SHARES_MAX_AGE = timedelta(days=7)


@dataclass
class IngestResult:
    companies: int = 0
    tickers: int = 0
    periods: int = 0
    errors: list[str] = field(default_factory=list)


def _read_csv(path: Path, member: str | None = None) -> pd.DataFrame | None:
    if not path.exists():
        return None
    if member is None:
        return pd.read_csv(path, sep=";", encoding="latin1", dtype=str)
    with zipfile.ZipFile(path) as zf:
        if member not in zf.namelist():
            return None
        with zf.open(member) as fh:
            return pd.read_csv(fh, sep=";", encoding="latin1", dtype=str)


def _listed_tickers(raw: Path, today: date) -> pd.DataFrame:
    frames = []
    for year in (today.year - 1, today.year):
        df = _read_csv(raw / f"fca_cia_aberta_{year}.zip", f"fca_cia_aberta_valor_mobiliario_{year}.csv")
        if df is not None:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames)
    df = df[df["Valor_Mobiliario"].isin(_SHARE_CLASSES) & df["Codigo_Negociacao"].notna()]
    df = df[df["Data_Fim_Negociacao"].isna()]
    return df.sort_values(["Data_Referencia", "Versao"]).groupby("Codigo_Negociacao", as_index=False).last()


def ingest(
    session: Session, today: date | None = None, download: bool = True, raw: Path | None = None
) -> IngestResult:
    today = today or date.today()
    raw = raw or cvm_files.RAW_DIR
    result = IngestResult()
    if download:
        result.errors += cvm_files.download_all(today, raw_dir=raw)

    tickers = _listed_tickers(raw, today)
    if tickers.empty:
        result.errors.append("arquivo FCA (tickers) indisponível")
        record_status(session, SOURCE_STATUS, False, "; ".join(result.errors))
        session.commit()
        return result
    listed = set(tickers["CNPJ_Companhia"])

    registry = _read_csv(raw / "cad_cia_aberta.csv")
    names = dict(zip(tickers["CNPJ_Companhia"], tickers["Nome_Empresarial"], strict=False))
    sectors: dict[str, tuple[str, str | None, str | None]] = {}
    if registry is not None:
        active = registry[registry["SIT"] == "ATIVO"]
        for r in active.itertuples():
            sectors.setdefault(
                r.CNPJ_CIA,
                (
                    r.CD_CVM,
                    r.SETOR_ATIV if isinstance(r.SETOR_ATIV, str) else None,
                    r.SIT_EMISSOR if isinstance(r.SIT_EMISSOR, str) else None,
                ),
            )

    for cnpj in listed:
        cd_cvm, sector, issuer_status = sectors.get(cnpj, (None, None, None))
        stmt = insert(Company).values(
            cnpj=cnpj,
            cd_cvm=cd_cvm,
            name=names.get(cnpj, cnpj),
            sector_cvm=sector,
            issuer_status=issuer_status,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["cnpj"],
                set_={
                    "cd_cvm": stmt.excluded.cd_cvm,
                    "name": stmt.excluded.name,
                    "sector_cvm": stmt.excluded.sector_cvm,
                    "issuer_status": stmt.excluded.issuer_status,
                },
            )
        )
        result.companies += 1
    for r in tickers.itertuples():
        stmt = insert(CompanyTicker).values(
            ticker=r.Codigo_Negociacao.strip().upper(),
            cnpj=r.CNPJ_Companhia,
            share_class=_SHARE_CLASSES[r.Valor_Mobiliario],
            unit_composition=r.Composicao_BDR_Unit if isinstance(r.Composicao_BDR_Unit, str) else None,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["ticker"],
                set_={
                    "cnpj": stmt.excluded.cnpj,
                    "share_class": stmt.excluded.share_class,
                    "unit_composition": stmt.excluded.unit_composition,
                },
            )
        )
        result.tickers += 1
    session.flush()

    capital: dict[str, CapitalComposition] = {}
    templates: dict[str, str] = {}
    latest_figures: dict[str, ParsedPeriod] = {}
    files = sorted(raw.glob("dfp_cia_aberta_*.zip")) + sorted(raw.glob("itr_cia_aberta_*.zip"))
    for path in files:
        doc = "DFP" if path.name.startswith("dfp") else "ITR"
        try:
            for period in parse_document(path, doc):
                if period.cnpj not in listed:
                    continue
                _upsert_period(session, period)
                result.periods += 1
                if not period.comparative:
                    previous = latest_figures.get(period.cnpj)
                    if previous is None or period.period_end >= previous.period_end:
                        latest_figures[period.cnpj] = period
                        templates[period.cnpj] = period.figures.template
            for comp in parse_capital(path, doc):
                if comp.cnpj in listed and (
                    comp.cnpj not in capital or comp.as_of >= capital[comp.cnpj].as_of
                ):
                    capital[comp.cnpj] = comp
        except Exception as err:  # noqa: BLE001 — one bad file must not stop the ingestion
            session.rollback()
            log.exception("failed to parse %s", path.name)
            result.errors.append(f"{path.name}: {err}")
        session.commit()

    for company in session.scalars(select(Company).where(Company.cnpj.in_(listed))):
        company.template = templates.get(company.cnpj, company.template)
        comp = capital.get(company.cnpj)
        if comp is not None and company.shares_source != "B3":
            fig = latest_figures.get(company.cnpj)
            count = from_cvm(
                comp, fig.figures.net_income_controlling if fig else None, fig.figures.eps if fig else None
            )
            _store_shares(company, count)
    _enrich_assets(session)
    record_status(session, SOURCE_STATUS, not result.errors, "; ".join(result.errors) or None)
    session.commit()
    return result


def _enrich_assets(session: Session) -> None:
    """Portfolio assets that are listed stocks get the CVM sector, name and the STOCK class (fixes the
    ambiguous '11' suffix of units); a class the user set by hand is kept."""
    rows = session.execute(
        select(Asset, Company)
        .join(CompanyTicker, CompanyTicker.ticker == Asset.ticker)
        .join(Company, Company.cnpj == CompanyTicker.cnpj)
    ).all()
    for asset, company in rows:
        asset.sector = company.sector_cvm
        asset.name = asset.name or company.name
        if not asset.class_confirmed:
            asset.asset_class = AssetClass.STOCK.value
            asset.class_confirmed = True


def _upsert_period(session: Session, p: ParsedPeriod) -> None:
    values = {
        "cnpj": p.cnpj,
        "doc_type": p.doc_type,
        "period_start": p.period_start,
        "period_end": p.period_end,
        "version": p.version,
        "received_on": p.received_on,
        "consolidated": p.consolidated,
        "comparative": p.comparative,
        "template": p.figures.template,
        "missing": ", ".join(p.figures.missing) or None,
    } | {c: getattr(p.figures, c) for c in _FIGURE_COLUMNS}
    stmt = insert(FundamentalPeriod).values(**values)
    excluded = stmt.excluded
    # Never let a prior-year comparative column overwrite the original document
    stmt = stmt.on_conflict_do_update(
        index_elements=["cnpj", "doc_type", "period_end"],
        set_={k: getattr(excluded, k) for k in values if k not in ("cnpj", "doc_type", "period_end")},
        where=(FundamentalPeriod.comparative.is_(True)) | (excluded.comparative.is_(False)),
    )
    session.execute(stmt)


def _store_shares(company: Company, count: ShareCount) -> None:
    company.shares_on, company.shares_pn = count.on, count.pn
    company.treasury_on, company.treasury_pn = count.treasury_on, count.treasury_pn
    company.shares_source, company.shares_as_of = count.source, count.as_of


def _stored_shares(company: Company) -> ShareCount | None:
    if company.shares_on is None:
        return None
    return ShareCount(
        on=company.shares_on,
        pn=company.shares_pn or Decimal(0),
        treasury_on=company.treasury_on or Decimal(0),
        treasury_pn=company.treasury_pn or Decimal(0),
        source=company.shares_source or "CVM",
        as_of=company.shares_as_of,
    )


# --- on-demand analysis -----------------------------------------------------------------------


class UnknownTickerError(LookupError):
    pass


@dataclass
class TickerFundamentals:
    ticker: str
    cnpj: str
    name: str
    sector: str | None
    template: str | None
    price: Decimal | None
    price_date: date | None
    shares: ShareCount | None
    result: FundamentalsResult
    previous_close: Decimal | None = None


def _refresh_shares(session: Session, company: Company, issuer: str, source, today: date) -> None:
    """Share counts and the "B3 lists cash dividends" flag, from the B3 listed-company data (weekly)."""
    fresh = (
        company.shares_source == "B3"
        and company.shares_as_of
        and today - company.shares_as_of < SHARES_MAX_AGE
        and company.b3_pays_dividends is not None
    )
    if fresh or source is None:
        return
    try:
        payload = source.supplement(issuer)
    except CorporateEventsError as err:
        log.warning("B3 share counts for %s failed: %s", issuer, err)
        return
    company.b3_pays_dividends = _pays_dividends(payload, today)
    count = from_b3(payload, _stored_shares(company), today)
    if count is not None:
        _store_shares(company, count)
    session.commit()


def _pays_dividends(payload: list[dict], today: date) -> bool:
    """Any cash dividend with a record date in the last ~13 months (the B3 lists about 12 months)."""
    since = today - timedelta(days=400)
    for company in payload or []:
        for item in company.get("cashDividends") or []:
            try:
                record = datetime.strptime(item.get("lastDatePrior") or "", "%d/%m/%Y").date()
            except ValueError:
                continue
            if record >= since:
                return True
    return False


def fetch_range(
    session: Session,
    provider: MarketDataProvider,
    ticker: str,
    start: date,
    end: date,
    resync: bool = False,
) -> None:
    """Fetch and cache daily bars of one ticker (raises MarketDataError on provider failure).
    `resync` also rewrites cached rows: open/high/low (rows cached before they were stored) and the
    split-adjusted close (a split after a row was cached changes it). The raw close is kept, except in
    the last days, where a row cached during the session holds an intraday price."""
    bars = provider.daily_bars([ticker], start, end).get(ticker, [])
    if resync:
        store_bars(
            session,
            ticker,
            bars,
            provider.name,
            update=("open", "high", "low", "close_adjusted"),
            recent_update=("close", "volume"),
            recent_from=end - REVISE,
        )
    else:
        store_bars(session, ticker, bars, provider.name)
    session.commit()


def ensure_recent_prices(
    session: Session, provider: MarketDataProvider | None, tickers: list[str], today: date
) -> list[str]:
    """Quotes for tickers outside the portfolio (analysis screen), last ~2 months, cached."""
    errors = []
    for ticker in tickers:
        last = session.scalar(select(func.max(PriceHistory.date)).where(PriceHistory.ticker == ticker))
        start = today - timedelta(days=LIQUIDITY_DAYS + 7) if last is None else last + timedelta(days=1)
        if provider is None or start > today or (last and (today - last).days < 1):
            continue
        try:
            fetch_range(session, provider, ticker, start, today)
        except MarketDataError as err:
            errors.append(str(err))
    return errors


def _latest_close(session: Session, ticker: str) -> tuple[Decimal | None, date | None]:
    row = session.execute(
        select(PriceHistory.close, PriceHistory.date)
        .where(PriceHistory.ticker == ticker)
        .order_by(PriceHistory.date.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else (None, None)


def _liquidity(session: Session, ticker: str, today: date) -> Decimal | None:
    since = today - timedelta(days=LIQUIDITY_DAYS)
    rows = session.execute(
        select(PriceHistory.close, PriceHistory.volume).where(
            PriceHistory.ticker == ticker, PriceHistory.date > since, PriceHistory.volume.is_not(None)
        )
    ).all()
    traded = [close * volume for close, volume in rows]
    return sum(traded, Decimal(0)) / len(traded) if traded else None


def fundamentals_for(
    session: Session,
    raw_ticker: str,
    market: MarketDataProvider | None = None,
    events_source=None,
    today: date | None = None,
) -> TickerFundamentals:
    today = today or date.today()
    try:
        ticker = normalize_ticker(raw_ticker)
    except InvalidTickerError as err:
        raise UnknownTickerError(raw_ticker) from err
    link = session.get(CompanyTicker, ticker)
    if link is None:
        raise UnknownTickerError(ticker)
    company = session.scalar(select(Company).where(Company.cnpj == link.cnpj))
    siblings = list(session.scalars(select(CompanyTicker).where(CompanyTicker.cnpj == company.cnpj)))

    _refresh_shares(session, company, ticker[:4], events_source, today)
    by_class: dict[str, str] = {}
    for s in sorted(siblings, key=lambda s: (s.ticker != ticker, s.ticker)):
        by_class.setdefault(s.share_class, s.ticker)
    wanted = sorted({ticker, *[t for c, t in by_class.items() if c in ("ON", "PN")]})
    ensure_recent_prices(session, market, wanted, today)

    price, price_date = _latest_close(session, ticker)
    previous_close = (
        session.scalar(
            select(PriceHistory.close)
            .where(PriceHistory.ticker == ticker, PriceHistory.date < price_date)
            .order_by(PriceHistory.date.desc())
            .limit(1)
        )
        if price_date
        else None
    )
    class_prices = {}
    for share_class in ("ON", "PN"):
        if share_class in by_class:
            close, _ = _latest_close(session, by_class[share_class])
            if close is not None:
                class_prices[share_class] = close
    periods = list(session.scalars(select(FundamentalPeriod).where(FundamentalPeriod.cnpj == company.cnpj)))
    shares = _stored_shares(company)
    if link.share_class == "UNIT" and shares:
        # Unit price → per-share figures need the unit composition (e.g. "1 ON / 2 PN")
        price = _unit_to_share_price(price, link.unit_composition)
        previous_close = _unit_to_share_price(previous_close, link.unit_composition)
    result = compute(
        periods,
        shares,
        price,
        class_prices,
        _liquidity(session, ticker, today),
        classify_sector(company.sector_cvm, company.template, ticker),
        company.template,
        issuer=ticker[:4],
        issuer_status=company.issuer_status,
        b3_pays_dividends=company.b3_pays_dividends,
        as_of=today,
    )
    if link.share_class == "UNIT":
        result.notes.append(f"unit ({link.unit_composition}): indicadores calculados por ação")
    return TickerFundamentals(
        ticker=ticker,
        cnpj=company.cnpj,
        name=company.name,
        sector=company.sector_cvm,
        template=company.template,
        price=price,
        price_date=price_date,
        shares=shares,
        result=result,
        previous_close=previous_close,
    )


def year_end_prices(session: Session, ticker: str, years: list[int]) -> dict[int, Decimal]:
    """Last split-adjusted close of December of each year (per share for units), for the indicator history."""
    link = session.get(CompanyTicker, ticker)
    out = {}
    for year in years:
        close = session.scalar(
            select(PriceHistory.close_adjusted)
            .where(
                PriceHistory.ticker == ticker,
                PriceHistory.date >= date(year, 12, 1),
                PriceHistory.date <= date(year, 12, 31),
            )
            .order_by(PriceHistory.date.desc())
            .limit(1)
        )
        if close is not None:
            if link is not None and link.share_class == "UNIT":
                close = _unit_to_share_price(close, link.unit_composition)
            out[year] = close
    return out


def _unit_to_share_price(price: Decimal | None, composition: str | None) -> Decimal | None:
    if price is None or not composition:
        return price
    counts = [int(n) for n in re.findall(r"(\d+)\s*(?:ON|PN)", composition.upper())]
    total = sum(counts)
    return price / total if total else price
