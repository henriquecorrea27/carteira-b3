"""Watchlist alert: tickers the user follows, reported ONLY by the price against the daily SMA200 (same SMA
and limits as the F8 chart analysis, `technical` in stocks.yaml). Each ticker falls in a zone; the alert
highlights the tickers whose zone changed since the last scheduled alert."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, Company, CompanyTicker, PriceHistory, WatchlistItem
from app.notifications.report import WEEKDAYS, _num, dmy, price
from app.rules.engine import load_rules
from app.rules.service import adjusted_closes, sync_history
from app.rules.technical import compute_technical

# ~275 sessions: enough for the SMA200 without fetching the 6-year history of the analysis
WATCH_DAYS = 400
CHEAP, BELOW, ABOVE, EXPENSIVE = "CHEAP", "BELOW", "ABOVE", "EXPENSIVE"
ZONE_ORDER = [CHEAP, BELOW, ABOVE, EXPENSIVE]
EMOJI = {CHEAP: "🟢", BELOW: "🟡", ABOVE: "🟠", EXPENSIVE: "🔴"}


@dataclass(frozen=True)
class Limits:
    sma_days: int
    cheap: Decimal  # e.g. −0.10
    expensive: Decimal  # e.g. +0.10


def limits() -> Limits:
    cfg = load_rules()["technical"]
    return Limits(int(cfg["sma_days"]), Decimal(str(cfg["cheap"])), Decimal(str(cfg["expensive"])))


def zone(distance: Decimal, lim: Limits) -> str:
    if distance <= lim.cheap:
        return CHEAP
    if distance < 0:
        return BELOW
    if distance < lim.expensive:
        return ABOVE
    return EXPENSIVE


def zone_label(z: str, lim: Limits) -> str:
    sma = f"MM{lim.sma_days}"
    return {
        CHEAP: f"{_num(abs(lim.cheap) * 100, 0)}% ou mais abaixo da {sma}",
        BELOW: f"abaixo da {sma}",
        ABOVE: f"acima da {sma}",
        EXPENSIVE: f"{_num(lim.expensive * 100, 0)}% ou mais acima da {sma}",
    }[z]


@dataclass
class WatchLine:
    ticker: str
    name: str | None
    note: str | None
    price: Decimal | None
    sma: Decimal | None
    distance: Decimal | None  # price / SMA − 1
    zone: str | None  # None → not enough history for the SMA
    sessions: int
    price_date: date | None


@dataclass
class ZoneChange:
    line: WatchLine
    previous: str


@dataclass
class WatchlistReport:
    day: date
    generated_at: datetime
    limits: Limits
    lines: list[WatchLine] = field(default_factory=list)
    changes: list[ZoneChange] = field(default_factory=list)
    has_baseline: bool = False
    late: bool = False

    @property
    def zones(self) -> dict[str, str]:
        """Baseline for the next alert (stored in report_dispatches.decisions)."""
        return {w.ticker: w.zone for w in self.lines if w.zone}


def _names(session: Session, tickers: list[str]) -> dict[str, str]:
    names = dict(
        session.execute(
            select(CompanyTicker.ticker, Company.name)
            .join(Company, Company.cnpj == CompanyTicker.cnpj)
            .where(CompanyTicker.ticker.in_(tickers))
        ).all()
    )
    for ticker, name in session.execute(select(Asset.ticker, Asset.name).where(Asset.ticker.in_(tickers))):
        if name:
            names[ticker] = name
    return names


def watch_lines(session: Session, today: date, market=None) -> list[WatchLine]:
    """Every watchlist ticker against its SMA, from the most below to the most above it. With `market`, the
    price history is re-synced first (once a day per ticker)."""
    lim = limits()
    items = session.scalars(select(WatchlistItem).order_by(WatchlistItem.ticker)).all()
    names = _names(session, [i.ticker for i in items])
    lines = []
    for item in items:
        if market is not None:
            sync_history(session, item.ticker, market, today, days=WATCH_DAYS)
        tech = compute_technical(
            adjusted_closes(session, item.ticker, today, lim.sma_days),
            {"sma_days": lim.sma_days, "cheap": lim.cheap, "expensive": lim.expensive},
        )
        last = session.scalar(
            select(func.max(PriceHistory.date)).where(
                PriceHistory.ticker == item.ticker, PriceHistory.date <= today
            )
        )
        lines.append(
            WatchLine(
                ticker=item.ticker,
                name=names.get(item.ticker),
                note=item.note,
                price=tech.price,
                sma=tech.sma,
                distance=tech.distance,
                zone=zone(tech.distance, lim) if tech.distance is not None else None,
                sessions=tech.sessions,
                price_date=last,
            )
        )
    lines.sort(key=lambda w: (w.distance is None, w.distance if w.distance is not None else 0, w.ticker))
    return lines


def build_watchlist(
    session: Session,
    day: date,
    now: datetime,
    baseline: dict[str, str] | None = None,
    market=None,
    late: bool = False,
) -> WatchlistReport:
    """`baseline`: zones of the previous scheduled alert (None → first alert, no changes section)."""
    report = WatchlistReport(day, now, limits(), watch_lines(session, day, market), late=late)
    report.has_baseline = baseline is not None
    for w in report.lines:
        previous = (baseline or {}).get(w.ticker)
        if w.zone and previous and previous != w.zone:
            report.changes.append(ZoneChange(w, previous))
    return report


def distance(value: Decimal | None) -> str:
    """Always one decimal and an explicit sign: +3,9% · −12,4% · 0,0%."""
    if value is None:
        return "—"
    v = round(value * 100, 1)
    sign = "+" if v > 0 else "−" if v < 0 else ""
    return f"{sign}{_num(abs(v), 1)}%"


def _line(w: WatchLine, lim: Limits) -> str:
    return f"**{w.ticker}** {price(w.price)} · MM{lim.sma_days} {price(w.sma)} · **{distance(w.distance)}**"


def render_watchlist(report: WatchlistReport) -> str:
    lim, day = report.limits, report.day
    out = [f"## 📈 Lista de observação · MM{lim.sma_days} · {WEEKDAYS[day.weekday()]}, {dmy(day)}"]
    if report.late:
        out.append(f"-# ⏰ Enviado com atraso em {report.generated_at:%d/%m às %H:%M}")
    if not report.lines:
        out.append("A lista está vazia. Adicione ações na aba Observação.")
        return "\n".join(out)

    out.append("")
    out.append("### 🔔 Mudanças de faixa")
    if not report.has_baseline:
        out.append("-# Primeiro aviso: as mudanças de faixa aparecem a partir do próximo.")
    elif report.changes:
        for c in report.changes:
            prev = f"{EMOJI[c.previous]} {zone_label(c.previous, lim)}"
            curr = f"{EMOJI[c.line.zone]} {zone_label(c.line.zone, lim)}"
            quote = f"{price(c.line.price)} ({distance(c.line.distance)})"
            out.append(f"**{c.line.ticker}**: {prev} → **{curr}** · {quote}")
    else:
        out.append("Nenhuma ação mudou de faixa.")

    for z in ZONE_ORDER:
        group = [w for w in report.lines if w.zone == z]
        if not group:
            continue
        out.append("")
        label = zone_label(z, lim)
        out.append(f"### {EMOJI[z]} {label[0].upper()}{label[1:]} ({len(group)})")
        for w in group:
            out.append(_line(w, lim))
            if w.note:
                out.append(f"-# {' '.join(w.note.split())[:160]}")

    missing = [w for w in report.lines if w.zone is None]
    if missing:
        out.append("")
        out.append(f"### ⚪ Sem MM{lim.sma_days}")
        for w in missing:
            why = "sem cotações" if w.price is None else f"só {w.sessions} pregões de histórico"
            out.append(f"**{w.ticker}** {price(w.price)} · {why}")

    dates = [w.price_date for w in report.lines if w.price_date]
    footer = f"Preços de {dmy(max(dates))}" if dates else "Sem cotações"
    out.append("")
    out.append(
        f"-# Distância = preço ÷ MM{lim.sma_days} − 1 (média dos últimos {lim.sma_days} fechamentos diários, "
        f"ajustados) · {footer} · gerado {report.generated_at:%d/%m %H:%M}"
    )
    return "\n".join(out)
