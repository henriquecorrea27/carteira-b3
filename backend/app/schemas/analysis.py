import datetime as dt

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Money, Number


class _Attrs(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IndicatorScoreOut(_Attrs):
    key: str
    label: str
    group: str
    value: Number | None
    unit: str
    range_label: str
    weight: float
    points: float | None
    status: str
    note: str | None


class EliminatoryOut(_Attrs):
    id: str
    label: str
    rule: str
    value_label: str | None
    passed: bool | None


class AnalysisOut(BaseModel):
    ticker: str
    name: str
    cnpj: str
    sector: str | None
    special_sector: str | None
    price: Number | None
    price_date: dt.date | None
    day_change: Number | None  # fraction vs. the previous close
    decision: str  # BUY | WAIT | AVOID
    score_final: float | None
    score_quality: float | None
    score_price: float | None
    quality_inconclusive: bool
    price_inconclusive: bool
    main_reason: str | None
    eliminatory: list[EliminatoryOut]
    indicators: list[IndicatorScoreOut]
    graham_price: Number | None
    graham_margin: Number | None
    bazin_price: Number | None
    dy_5y: Number | None
    market_cap: Money | None
    last_dfp: dt.date | None
    last_itr: dt.date | None
    received_on: dt.date | None
    warnings: list[str]
    rules_version: int


def analysis_out(ta) -> AnalysisOut:
    """`ta` is an app.rules.service.TickerAnalysis."""
    f, a = ta.fundamentals, ta.analysis
    r = f.result
    return AnalysisOut(
        ticker=f.ticker,
        name=f.name,
        cnpj=f.cnpj,
        sector=f.sector,
        special_sector=a.special_sector,
        price=f.price,
        price_date=f.price_date,
        day_change=f.price / f.previous_close - 1 if f.price and f.previous_close else None,
        decision=a.decision.value,
        score_final=a.score_final,
        score_quality=a.score_quality,
        score_price=a.score_price,
        quality_inconclusive=a.quality_inconclusive,
        price_inconclusive=a.price_inconclusive,
        main_reason=a.main_reason,
        eliminatory=[EliminatoryOut.model_validate(c) for c in a.eliminatory],
        indicators=[IndicatorScoreOut.model_validate(i) for i in a.indicators],
        graham_price=r.value("graham_price"),
        graham_margin=r.value("graham_margin"),
        bazin_price=r.value("bazin_price"),
        dy_5y=r.value("dy_5y"),
        market_cap=r.value("market_cap"),
        last_dfp=r.last_dfp,
        last_itr=r.last_itr,
        received_on=r.received_on,
        warnings=a.warnings,
        rules_version=a.rules_version,
    )


def analysis_details(ta) -> dict:
    """JSON stored in analysis_snapshots.details (same shape as the API response)."""
    return analysis_out(ta).model_dump(mode="json")


class RulesSummaryOut(BaseModel):
    """Latest decision of a portfolio stock (shown in the positions table)."""

    decision: str
    score_final: float | None
    score_quality: float | None
    score_price: float | None
    inconclusive: bool
    main_reason: str | None
    date: dt.date


class PriceBarOut(BaseModel):
    date: dt.date
    open: Number | None
    high: Number | None
    low: Number | None
    close: Number
    volume: Number | None


class PortfolioRunOut(BaseModel):
    analyzed: list[str]
    skipped: list[str]
    errors: list[str]
