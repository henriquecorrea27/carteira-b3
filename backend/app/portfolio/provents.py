"""Provent read models: detailed list, monthly evolution, year × month table, per-asset split, agenda."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.portfolio.dashboard import DashboardContext
from app.portfolio.types import ProventStatus

ZERO = Decimal(0)


@dataclass
class ProventView:
    id: int
    ticker: str
    asset_class: str
    type: str
    status: str
    record_date: date
    payment_date: date | None
    quantity: Decimal
    value_per_share: Decimal | None
    gross_amount: Decimal
    tax_withheld: Decimal
    net_amount: Decimal
    source: str


def _effective_status(status: str | None, payment_date: date | None, today: date) -> str:
    if status == ProventStatus.ANNOUNCED and payment_date and payment_date <= today:
        return ProventStatus.PAID.value
    return status or ProventStatus.PAID.value


def list_provents(
    ctx: DashboardContext, year: int | None = None, ticker: str | None = None, status: str | None = None
) -> list[ProventView]:
    out = []
    for r in ctx.provent_rows:
        eff = _effective_status(r.status, r.payment_date, ctx.today)
        pay = r.payment_date or r.date
        if (year and pay.year != year) or (ticker and r.ticker != ticker) or (status and eff != status):
            continue
        out.append(
            ProventView(
                id=r.id,
                ticker=r.ticker,
                asset_class=ctx.asset_class(r.ticker).value,
                type=r.type,
                status=eff,
                record_date=r.date,
                payment_date=r.payment_date,
                quantity=r.quantity,
                value_per_share=r.price,
                gross_amount=r.gross_amount or ZERO,
                tax_withheld=r.tax_withheld or ZERO,
                net_amount=r.net_amount or ZERO,
                source=r.source,
            )
        )
    return sorted(out, key=lambda p: (p.payment_date or p.record_date, p.ticker), reverse=True)


@dataclass
class MonthBucket:
    month: str  # YYYY-MM
    received: Decimal
    receivable: Decimal


@dataclass
class YearRow:
    year: int
    months: list[Decimal]  # 12 values, Jan..Dec
    total: Decimal
    monthly_avg: Decimal


@dataclass
class AssetShare:
    ticker: str
    net_amount: Decimal
    pct: Decimal


@dataclass
class ProventsSummary:
    total_received: Decimal
    received_12m: Decimal
    monthly_avg_12m: Decimal
    receivable: Decimal
    monthly: list[MonthBucket]
    by_year: list[YearRow]
    by_asset_12m: list[AssetShare]
    upcoming: list[ProventView]


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def provents_summary(ctx: DashboardContext, months_back: int = 12) -> ProventsSummary:
    rows = list_provents(ctx)
    today = ctx.today
    received = [p for p in rows if p.status != ProventStatus.ANNOUNCED]
    announced = [p for p in rows if p.status == ProventStatus.ANNOUNCED]
    year_ago = today - timedelta(days=365)
    last_12m = [p for p in received if p.payment_date and year_ago < p.payment_date <= today]

    # Monthly buckets: last `months_back` months plus any future month with announced payments
    first = date(today.year, today.month, 1)
    for _ in range(months_back - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    buckets: dict[str, MonthBucket] = {}
    cursor = first
    last_future = max((p.payment_date for p in announced if p.payment_date), default=today)
    while cursor <= max(today, last_future):
        key = _month_key(cursor)
        buckets[key] = MonthBucket(key, ZERO, ZERO)
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    for p in rows:
        key = _month_key(p.payment_date or p.record_date)
        if key in buckets:
            if p.status == ProventStatus.ANNOUNCED:
                buckets[key].receivable += p.net_amount
            else:
                buckets[key].received += p.net_amount

    years: dict[int, list[Decimal]] = defaultdict(lambda: [ZERO] * 12)
    for p in received:
        pay = p.payment_date or p.record_date
        years[pay.year][pay.month - 1] += p.net_amount
    by_year = []
    for year in sorted(years, reverse=True):
        months = years[year]
        elapsed = today.month if year == today.year else 12
        total = sum(months, ZERO)
        by_year.append(YearRow(year, months, total, total / elapsed))

    per_asset: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in last_12m:
        per_asset[p.ticker] += p.net_amount
    total_12m = sum(per_asset.values(), ZERO)
    by_asset = sorted(
        (AssetShare(t, v, v / total_12m if total_12m else ZERO) for t, v in per_asset.items()),
        key=lambda a: a.net_amount,
        reverse=True,
    )
    return ProventsSummary(
        total_received=sum((p.net_amount for p in received), ZERO),
        received_12m=total_12m,
        monthly_avg_12m=total_12m / 12,
        receivable=sum((p.net_amount for p in announced), ZERO),
        monthly=list(buckets.values()),
        by_year=by_year,
        by_asset_12m=by_asset,
        upcoming=sorted(announced, key=lambda p: p.payment_date or p.record_date),
    )
