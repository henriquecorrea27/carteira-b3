"""Portfolio engine: rebuilds positions, average price (custo médio ponderado, Receita Federal
method), realized results and provents from the transaction ledger.

Pure and deterministic — no database or network access — so every rule can be tested with
closed numeric cases. Values are kept at full Decimal precision; rounding happens on output.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.portfolio.types import PROVENT_TYPES, ProventStatus, TransactionType

ZERO = Decimal(0)

# Same-day ordering: corporate events take effect at the start of the ex-date, so trades on that
# day are already in post-event terms. Buys run before sells so a same-day buy+sell never looks
# like an oversell (day trade is out of scope). Fraction auctions settle after the event.
_DAY_PRIORITY = {
    TransactionType.TICKER_CHANGE: 0,
    TransactionType.SPLIT: 1,
    TransactionType.REVERSE_SPLIT: 1,
    TransactionType.BONUS: 2,
    TransactionType.BUY: 3,
    TransactionType.SELL: 4,
    TransactionType.FRACTION_AUCTION: 5,
    TransactionType.DIVIDEND: 6,
    TransactionType.JCP: 6,
    TransactionType.INCOME: 6,
}


@dataclass(frozen=True)
class LedgerEntry:
    """Engine view of a transaction.

    Field meaning per type:
    - BUY/SELL/FRACTION_AUCTION: quantity, price (unit), costs.
    - SPLIT/REVERSE_SPLIT: factor k (new shares per old share for SPLIT; old per new for REVERSE_SPLIT).
    - BONUS: quantity of new shares, price = unit cost attributed by the company (None = pending).
    - TICKER_CHANGE: ticker (old), target_ticker (new), factor (new shares per old share).
    - DIVIDEND/JCP/INCOME: quantity (shares on record date), price (value per share),
      gross_amount / tax_withheld / net_amount, payment_date, status.
    """

    date: date
    ticker: str
    type: TransactionType
    quantity: Decimal = ZERO
    price: Decimal | None = None
    costs: Decimal = ZERO
    factor: Decimal | None = None
    target_ticker: str | None = None
    gross_amount: Decimal | None = None
    tax_withheld: Decimal | None = None
    net_amount: Decimal | None = None
    payment_date: date | None = None
    status: ProventStatus | None = None
    id: int | None = None
    seq: int = 0

    @property
    def provent_gross(self) -> Decimal:
        if self.gross_amount is not None:
            return self.gross_amount
        return self.quantity * (self.price or ZERO)

    @property
    def provent_tax(self) -> Decimal:
        return self.tax_withheld or ZERO

    @property
    def provent_net(self) -> Decimal:
        if self.net_amount is not None:
            return self.net_amount
        return self.provent_gross - self.provent_tax

    @property
    def is_received(self) -> bool:
        return self.status in (None, ProventStatus.PAID, ProventStatus.CONFIRMED)


class LedgerError(Exception):
    def __init__(self, code: str, message: str, entry: LedgerEntry):
        super().__init__(message)
        self.code = code
        self.message = message
        self.entry = entry


@dataclass
class Position:
    ticker: str
    quantity: Decimal = ZERO
    total_cost: Decimal = ZERO
    realized_result: Decimal = ZERO
    provents_gross: Decimal = ZERO
    provents_tax: Decimal = ZERO
    provents_net: Decimal = ZERO
    provents_receivable_net: Decimal = ZERO
    pending_bonus_cost: bool = False
    first_date: date | None = None

    @property
    def avg_price(self) -> Decimal:
        return self.total_cost / self.quantity if self.quantity else ZERO

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


@dataclass(frozen=True)
class RealizedSale:
    date: date
    ticker: str
    quantity: Decimal
    proceeds: Decimal
    cost_basis: Decimal
    result: Decimal
    entry_id: int | None


@dataclass
class PortfolioResult:
    positions: dict[str, Position] = field(default_factory=dict)
    sales: list[RealizedSale] = field(default_factory=list)

    def position(self, ticker: str) -> Position:
        return self.positions.get(ticker) or Position(ticker)

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions.values() if p.is_open]


def sort_entries(entries: Iterable[LedgerEntry]) -> list[LedgerEntry]:
    return sorted(entries, key=lambda e: (e.date, _DAY_PRIORITY[e.type], e.seq, e.id or 0))


def build_portfolio(entries: Iterable[LedgerEntry], until: date | None = None) -> PortfolioResult:
    """Replay the ledger in chronological order. `until` is inclusive (end of that day)."""
    result = PortfolioResult()
    for entry in sort_entries(entries):
        if until is not None and entry.date > until:
            break
        _apply(result, entry)
    return result


def quantity_on(entries: Iterable[LedgerEntry], ticker: str, day: date) -> Decimal:
    """Shares held at the end of `day` (used for the record date / data-com of provents)."""
    return build_portfolio(entries, until=day).position(ticker).quantity


def _fmt(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


def _get(result: PortfolioResult, ticker: str, day: date) -> Position:
    pos = result.positions.get(ticker)
    if pos is None:
        pos = result.positions[ticker] = Position(ticker, first_date=day)
    return pos


def _apply(result: PortfolioResult, e: LedgerEntry) -> None:
    match e.type:
        case TransactionType.BUY:
            _buy(result, e)
        case TransactionType.SELL | TransactionType.FRACTION_AUCTION:
            _sell(result, e)
        case TransactionType.SPLIT:
            _split(result, e, inverse=False)
        case TransactionType.REVERSE_SPLIT:
            _split(result, e, inverse=True)
        case TransactionType.BONUS:
            _bonus(result, e)
        case TransactionType.TICKER_CHANGE:
            _ticker_change(result, e)
        case t if t in PROVENT_TYPES:
            _provent(result, e)
        case _:
            raise LedgerError("UNKNOWN_TYPE", f"tipo de lançamento não suportado: {e.type}", e)


def _require_positive(e: LedgerEntry, value: Decimal | None, name: str) -> Decimal:
    if value is None or value <= 0:
        raise LedgerError(
            "INVALID_VALUE", f"{e.type} {e.ticker} em {e.date:%d/%m/%Y}: {name} deve ser maior que zero", e
        )
    return value


def _buy(result: PortfolioResult, e: LedgerEntry) -> None:
    qty = _require_positive(e, e.quantity, "quantidade")
    price = e.price if e.price is not None else ZERO
    if price < 0 or e.costs < 0:
        raise LedgerError(
            "INVALID_VALUE", f"Compra de {e.ticker} em {e.date:%d/%m/%Y}: preço ou custos negativos", e
        )
    pos = _get(result, e.ticker, e.date)
    if pos.quantity == 0:
        pos.total_cost = ZERO
    pos.total_cost += qty * price + e.costs
    pos.quantity += qty


def _sell(result: PortfolioResult, e: LedgerEntry) -> None:
    qty = _require_positive(e, e.quantity, "quantidade")
    pos = _get(result, e.ticker, e.date)
    if qty > pos.quantity:
        raise LedgerError(
            "INSUFFICIENT_POSITION",
            f"Venda de {_fmt(qty)} {e.ticker} em {e.date:%d/%m/%Y} maior que a posição "
            f"na data ({_fmt(pos.quantity)})",
            e,
        )
    proceeds = qty * (e.price or ZERO) - e.costs
    # Closing the whole position takes the exact remaining cost (no rounding residue)
    cost_basis = pos.total_cost if qty == pos.quantity else qty * pos.avg_price
    pos.total_cost -= cost_basis
    pos.quantity -= qty
    if pos.quantity == 0:
        pos.total_cost = ZERO
        pos.pending_bonus_cost = False
    sale_result = proceeds - cost_basis
    pos.realized_result += sale_result
    result.sales.append(RealizedSale(e.date, e.ticker, qty, proceeds, cost_basis, sale_result, e.id))


def _split(result: PortfolioResult, e: LedgerEntry, *, inverse: bool) -> None:
    factor = _require_positive(e, e.factor, "fator")
    pos = result.positions.get(e.ticker)
    if pos is None or pos.quantity == 0:
        return
    # Total cost is preserved, so PM ÷ k (split) or PM × k (reverse split) follows automatically.
    pos.quantity = pos.quantity / factor if inverse else pos.quantity * factor


def _bonus(result: PortfolioResult, e: LedgerEntry) -> None:
    qty = _require_positive(e, e.quantity, "quantidade")
    pos = result.positions.get(e.ticker)
    if pos is None or pos.quantity == 0:
        raise LedgerError(
            "NO_POSITION", f"Bonificação de {e.ticker} em {e.date:%d/%m/%Y} sem posição na data", e
        )
    if e.price is None:
        pos.pending_bonus_cost = True
    else:
        if e.price < 0:
            raise LedgerError("INVALID_VALUE", f"Bonificação de {e.ticker}: custo atribuído negativo", e)
        pos.total_cost += qty * e.price
    pos.quantity += qty


def _ticker_change(result: PortfolioResult, e: LedgerEntry) -> None:
    factor = _require_positive(e, e.factor, "fator")
    if not e.target_ticker or e.target_ticker == e.ticker:
        raise LedgerError("INVALID_VALUE", f"Troca de ticker de {e.ticker}: ticker de destino inválido", e)
    old = result.positions.get(e.ticker)
    if old is None or old.quantity == 0:
        return
    new = _get(result, e.target_ticker, e.date)
    if new.quantity == 0:
        new.total_cost = ZERO
    new.quantity += old.quantity * factor
    new.total_cost += old.total_cost
    new.pending_bonus_cost = new.pending_bonus_cost or old.pending_bonus_cost
    old.quantity = ZERO
    old.total_cost = ZERO
    old.pending_bonus_cost = False


def _provent(result: PortfolioResult, e: LedgerEntry) -> None:
    pos = _get(result, e.ticker, e.date)
    if e.is_received:
        pos.provents_gross += e.provent_gross
        pos.provents_tax += e.provent_tax
        pos.provents_net += e.provent_net
    else:
        pos.provents_receivable_net += e.provent_net
