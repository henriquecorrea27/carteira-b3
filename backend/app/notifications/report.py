"""Daily report (CLAUDE.md §6.2): built from the ledger, cached prices and the latest rule snapshots, then
rendered as Discord-flavoured Markdown in Portuguese."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.calendar import is_business_day, next_business_day
from app.corporate_events.service import agenda, pending
from app.market_data.service import source_statuses
from app.portfolio.dashboard import DashboardContext, positions, summary
from app.portfolio.types import PROVENT_TYPES, AssetClass
from app.rules.service import latest_snapshots

DECISIONS = {"BUY": "🟢 Comprar", "WAIT": "🟡 Aguardar", "AVOID": "🔴 Evitar"}
DECISION_ORDER = ["BUY", "WAIT", "AVOID"]
PROVENT_LABELS = {"DIVIDEND": "Dividendo", "JCP": "JCP", "INCOME": "Rendimento"}
EVENT_LABELS = {"SPLIT": "Desdobramento", "REVERSE_SPLIT": "Grupamento", "BONUS": "Bonificação"}
SOURCE_LABELS = {
    "prices": "cotações (yfinance)",
    "ibov": "IBOV (yfinance)",
    "cdi": "CDI (Banco Central)",
    "corporate_events": "proventos e eventos (B3)",
    "cvm": "dados da CVM",
}
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
UPCOMING_BUSINESS_DAYS = 5
MAX_PAID_WINDOW = timedelta(days=31)


@dataclass
class StockLine:
    ticker: str
    decision: str
    score: Decimal | None
    price: Decimal | None
    change: Decimal | None
    reason: str | None
    inconclusive: bool
    analyzed_on: date
    score_quality: float | None = None  # tie-breaks (stocks.yaml decision.tie_break)
    liquidity: float | None = None
    sma_distance: Decimal | None = None  # price / SMA − 1 (F8 chart analysis)
    sma_days: int = 200


@dataclass
class OtherLine:
    ticker: str
    asset_class: str
    price: Decimal | None
    change: Decimal | None


@dataclass
class ChangeLine:
    ticker: str
    previous: str
    current: str
    score: Decimal | None


@dataclass
class PaidLine:
    ticker: str
    kind: str
    payment_date: date
    net: Decimal


@dataclass
class UpcomingLine:
    ticker: str
    kind: str
    record_date: date
    payment_date: date | None
    value: Decimal
    factor: Decimal | None
    estimated_net: Decimal | None


@dataclass
class DailyReport:
    day: date
    generated_at: datetime
    late: bool = False
    market_value: Decimal | None = None
    day_change: Decimal | None = None
    return_12m: Decimal | None = None
    ibov_12m: Decimal | None = None
    cdi_12m: Decimal | None = None
    receivable: Decimal = Decimal(0)
    has_baseline: bool = False
    changes: list[ChangeLine] = field(default_factory=list)
    stocks: list[StockLine] = field(default_factory=list)
    unanalyzed: list[str] = field(default_factory=list)
    others: list[OtherLine] = field(default_factory=list)
    paid_since: date | None = None
    paid: list[PaidLine] = field(default_factory=list)
    upcoming_until: date | None = None
    upcoming: list[UpcomingLine] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    prices_as_of: date | None = None
    last_dfp: date | None = None
    last_itr: date | None = None

    @property
    def decisions(self) -> dict[str, str]:
        return {s.ticker: s.decision for s in self.stocks}


def add_business_days(day: date, n: int) -> date:
    for _ in range(n):
        day = next_business_day(day)
    return day


def last_business_day(day: date) -> date:
    while not is_business_day(day):
        day -= timedelta(days=1)
    return day


def build_report(
    session: Session,
    day: date,
    now: datetime,
    baseline: dict[str, str] | None = None,
    paid_since: date | None = None,
    late: bool = False,
) -> DailyReport:
    """`baseline`: decisions of the previous report (None → first report, no changes section).
    `paid_since`: provents paid after this date are listed (defaults to the report day only)."""
    today = now.date()
    # Positions and the day's change as of the report day (a late report on a weekend must not compare
    # Saturday with Friday)
    ctx = DashboardContext(session, day)
    views = [v for v in positions(ctx) if v.quantity > 0]
    report = DailyReport(day=day, generated_at=now, late=late, has_baseline=baseline is not None)

    if views:
        s = summary(ctx)
        report.market_value, report.day_change = s.market_value, s.day_change
        report.return_12m, report.ibov_12m, report.cdi_12m = s.return_12m, s.ibov_12m, s.cdi_12m
        report.prices_as_of = s.prices_as_of
        report.receivable = s.provents_receivable

    snapshots = latest_snapshots(session, [v.ticker for v in views])
    for v in views:
        snap = snapshots.get(v.ticker)
        if v.asset_class != AssetClass.STOCK:
            report.others.append(OtherLine(v.ticker, v.asset_class.value, v.current_price, v.day_change_pct))
        elif snap is None:
            report.unanalyzed.append(v.ticker)
        else:
            technical = (snap.details or {}).get("technical") or {}
            distance = technical.get("distance")
            report.stocks.append(
                StockLine(
                    ticker=v.ticker,
                    decision=snap.decision,
                    score=snap.score_final,
                    price=v.current_price,
                    change=v.day_change_pct,
                    reason=snap.main_reason,
                    inconclusive=snap.inconclusive,
                    analyzed_on=snap.date,
                    score_quality=snap.score_quality,
                    liquidity=float((snap.details or {}).get("daily_liquidity") or 0),
                    sma_distance=Decimal(str(distance)) if distance is not None else None,
                    sma_days=technical.get("sma_days") or 200,
                )
            )
    # Ties: final score → quality score → daily liquidity (stocks.yaml decision.tie_break)
    report.stocks.sort(
        key=lambda s: (
            DECISION_ORDER.index(s.decision),
            -(s.score or 0),
            -(s.score_quality or 0),
            -(s.liquidity or 0),
            s.ticker,
        )
    )
    dfps = [s.last_dfp for s in snapshots.values() if s.last_dfp]
    itrs = [s.last_itr for s in snapshots.values() if s.last_itr]
    report.last_dfp, report.last_itr = max(dfps, default=None), max(itrs, default=None)

    if baseline is not None:
        for s in report.stocks:
            before = baseline.get(s.ticker)
            if before and before != s.decision:
                report.changes.append(ChangeLine(s.ticker, before, s.decision, s.score))

    # Provents paid since the previous report (only the report day on the first one or after a long gap)
    start = paid_since if paid_since and day - paid_since <= MAX_PAID_WINDOW else day - timedelta(days=1)
    report.paid_since = start
    for r in ctx.provent_rows:
        if r.payment_date and start < r.payment_date <= day and r.payment_date <= today:
            report.paid.append(PaidLine(r.ticker, r.type, r.payment_date, r.net_amount or Decimal(0)))
    report.paid.sort(key=lambda p: (p.payment_date, p.ticker))

    report.upcoming_until = add_business_days(day, UPCOMING_BUSINESS_DAYS)
    for item in agenda(session, today):
        if day < item.record_date <= report.upcoming_until:
            report.upcoming.append(
                UpcomingLine(
                    item.ticker,
                    item.kind,
                    item.record_date,
                    item.payment_date,
                    item.value,
                    item.factor,
                    item.estimated_net,
                )
            )
    report.upcoming.sort(key=lambda u: (u.record_date, u.ticker))

    report.pending = _pending_lines(session, report, today)
    return report


def _pending_lines(session: Session, report: DailyReport, today: date) -> list[str]:
    lines = []
    issues = pending(session, today)
    bonus = Counter(p.ticker for p in issues if p.kind == "BONUS_NO_COST")
    if bonus:
        total = sum(bonus.values())
        tickers = ", ".join(f"{t} ({n})" if n > 1 else t for t, n in sorted(bonus.items()))
        noun = "bonificação" if total == 1 else "bonificações"
        lines.append(f"{total} {noun} sem custo atribuído: {tickers} — o PM desses ativos está incompleto")
    for p in issues:
        if p.kind == "UNRECOGNIZED_EVENT":
            lines.append(f"Evento não reconhecido em {p.ticker} ({dmy(p.date)}) — confira se afeta a posição")
    for status in source_statuses(session):
        if not status.ok:
            label = SOURCE_LABELS.get(status.source, status.source)
            since = ""
            if status.last_success_at:
                since = f" · último sucesso {dmy(status.last_success_at.astimezone().date())}"
            message = _clip(status.message or "erro desconhecido", 140)
            lines.append(f"Falha na fonte {label}: {message}{since}")
    inconclusive = [s.ticker for s in report.stocks if s.inconclusive]
    if inconclusive:
        lines.append(f"Nota inconclusiva (dados insuficientes): {', '.join(inconclusive)}")
    if report.unanalyzed:
        lines.append(f"Sem análise das regras: {', '.join(report.unanalyzed)}")
    stale = [s.ticker for s in report.stocks if (report.day - s.analyzed_on).days > 3]
    if stale:
        lines.append(f"Análise desatualizada (mais de 3 dias): {', '.join(stale)}")
    return lines


# --- rendering --------------------------------------------------------------------------------


def _num(value: Decimal | float, decimals: int) -> str:
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def brl(value: Decimal | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    text = f"R$ {_num(abs(value), 2)}"
    if value < 0:
        return f"−{text}"
    return f"+{text}" if signed else text


def pct(value: Decimal | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    text = f"{_num(abs(value) * 100, 1 if abs(value) >= Decimal('0.1') else 2)}%"
    if value < 0:
        return f"−{text}"
    return f"+{text}" if signed and value > 0 else text


def price(value: Decimal | None) -> str:
    return "—" if value is None else f"R$ {_num(value, 2)}"


def dmy(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def dm(day: date) -> str:
    return day.strftime("%d/%m")


def _clip(text: str, size: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= size else text[: size - 1] + "…"


def _score(value: Decimal | None) -> str:
    return "nota —" if value is None else f"nota {_num(value, 1)}"


def _sma(s: StockLine) -> str:
    """Distance from the SMA200, always with one decimal (e.g. "MM200 +3,9%")."""
    if s.sma_distance is None:
        return ""
    value = round(s.sma_distance * 100, 1)
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f" · MM{s.sma_days} {sign}{_num(abs(value), 1)}%"


def _quote(p: Decimal | None, change: Decimal | None) -> str:
    return price(p) + (f" ({pct(change)})" if change is not None else "")


def render(report: DailyReport) -> str:
    day = report.day
    out = [f"## 📊 Carteira B3 · {WEEKDAYS[day.weekday()]}, {dmy(day)}"]
    if report.late:
        out.append(
            f"-# ⏰ Enviado com atraso em {report.generated_at:%d/%m às %H:%M} "
            "(o computador estava desligado no horário)"
        )

    if report.market_value is not None:
        # Only percentages: the report does not show the patrimony in R$
        if report.day_change is not None:
            base = report.market_value - report.day_change
            change_pct = report.day_change / base if base else None
            out.append(f"**Carteira no dia:** {pct(change_pct)}")
        if report.return_12m is not None:
            out.append(
                f"-# 12 meses: carteira {pct(report.return_12m)} · IBOV {pct(report.ibov_12m)} · "
                f"CDI {pct(report.cdi_12m)}"
            )
    else:
        out.append("Nenhuma posição aberta na carteira.")

    out.append("")
    out.append("### 🔔 Mudanças desde o último relatório")
    if not report.has_baseline:
        out.append("-# Primeiro relatório: as mudanças de decisão aparecem a partir do próximo.")
    elif report.changes:
        for c in report.changes:
            change = f"{DECISIONS[c.previous]} → **{DECISIONS[c.current]}**"
            out.append(f"**{c.ticker}**: {change} · {_score(c.score)}")
    else:
        out.append("Nenhuma ação mudou de decisão.")

    for decision in DECISION_ORDER:
        group = [s for s in report.stocks if s.decision == decision]
        if not group:
            continue
        out.append("")
        out.append(f"### {DECISIONS[decision]} ({len(group)})")
        for s in group:
            line = f"**{s.ticker}** · {_score(s.score)} · {_quote(s.price, s.change)}{_sma(s)}"
            if s.inconclusive:
                line += " · inconclusiva"
            out.append(line)
            if s.reason:
                out.append(f"-# {_clip(s.reason, 160)}")

    if report.others:
        out.append("")
        out.append("### Outros ativos (sem regras)")
        out.append(" · ".join(f"**{o.ticker}** {_quote(o.price, o.change)}" for o in report.others))

    out.append("")
    out.append("### 💰 Proventos")
    if report.paid:
        single_day = report.paid_since is None or day - report.paid_since <= timedelta(days=1)
        title = "Pagos hoje" if single_day else f"Pagos desde {dm(report.paid_since + timedelta(days=1))}"
        total = sum((p.net for p in report.paid), Decimal(0))
        out.append(f"{title}: **{brl(total)}** líquido")
        for p in report.paid:
            when = "" if single_day else f" · {dm(p.payment_date)}"
            out.append(f"- **{p.ticker}** {PROVENT_LABELS.get(p.kind, p.kind)} {brl(p.net)}{when}")
    else:
        out.append("Nenhum provento pago hoje.")
    if report.upcoming:
        out.append(f"Datas-com até {dm(report.upcoming_until)} (compre até a data-com para ter direito):")
        for u in report.upcoming:
            if u.kind in PROVENT_TYPES:
                text = f"{PROVENT_LABELS.get(u.kind, u.kind)} R$ {_num(u.value, 4)}/ação"
                if u.estimated_net is not None:
                    text += f" (≈ {brl(u.estimated_net)} líquido)"
                if u.payment_date:
                    text += f" · paga {dm(u.payment_date)}"
            else:
                text = EVENT_LABELS.get(u.kind, u.kind)
                if u.factor is not None:
                    text += f" fator {_num(u.factor, 4).rstrip('0').rstrip(',')}"
            out.append(f"- **{u.ticker}** com {dm(u.record_date)} · {text}")
    else:
        out.append(f"-# Nenhuma data-com até {dm(report.upcoming_until)}.")
    if report.receivable:
        out.append(f"-# A receber (já anunciados): {brl(report.receivable)} líquido")

    if report.pending:
        out.append("")
        out.append("### ⚠️ Pendências")
        out.extend(f"- {line}" for line in report.pending)

    footer = [f"Preços de {dmy(report.prices_as_of)}" if report.prices_as_of else "Sem cotações"]
    if report.last_dfp:
        footer.append(f"DFP {dmy(report.last_dfp)}")
    if report.last_itr:
        footer.append(f"ITR {dmy(report.last_itr)}")
    out.append("")
    out.append("-# " + " · ".join(footer) + f" · gerado {report.generated_at:%d/%m %H:%M}")
    return "\n".join(out)
