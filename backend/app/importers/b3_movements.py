"""B3 Área do Investidor — 'Movimentação' export → provents and corporate events actually credited.
Layout and the meaning of each 'Movimentação' value are documented in tests/fixtures/b3/README.md."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.importers.base import (
    Candidate,
    ImportRow,
    RowStatus,
    normalize_broker,
    row_hash,
    stringify,
    to_date,
    to_decimal,
)
from app.portfolio.tax import default_tax_table
from app.portfolio.tickers import InvalidTickerError, normalize_ticker
from app.portfolio.types import ProventStatus, TransactionType

T = TransactionType
CENT = Decimal("0.01")
HEADER = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]

PROVENTS = {
    "Dividendo": T.DIVIDEND,
    "Juros Sobre Capital Próprio": T.JCP,
    "Rendimento": T.INCOME,
}
EVENTS = {
    "Bonificação em Ativos": T.BONUS,
    "Leilão de Fração": T.FRACTION_AUCTION,
    "Desdobro": T.SPLIT,
    "Grupamento": T.REVERSE_SPLIT,
}
IGNORED = {
    "Transferência - Liquidação": "liquidação de negócio (já vem no extrato de Negociação)",
    "Transferência": "transferência de custódia entre corretoras",
    "Juros Sobre Capital Próprio - Transferido": "provento transferido entre corretoras",
    "Dividendo - Transferido": "provento transferido entre corretoras",
    "Rendimento - Transferido": "provento transferido entre corretoras",
    "Atualização": "atualização informativa da posição",
    "Fração em Ativos": "débito da fração enviada a leilão (o crédito vem em 'Leilão de Fração')",
    "Direito de Subscrição": "direito de subscrição (não exercido)",
    "Direitos de Subscrição - Não Exercido": "direito de subscrição não exercido",
    "Cessão de Direitos": "cessão de direitos de subscrição",
    "Cessão de Direitos - Solicitada": "cessão de direitos de subscrição",
    "Compra": "compra/venda vem do extrato de Negociação",
    "Venda": "compra/venda vem do extrato de Negociação",
}
FIXED_INCOME_PREFIXES = ("CDB", "LCI", "LCA", "CRI", "CRA", "TESOURO", "DEBENTURE", "LF ")


class B3MovementsImporter:
    name = "b3_movimentacao"

    def matches(self, sheet_name: str, header: list[str]) -> bool:
        return header[: len(HEADER)] == HEADER

    def parse(self, file_name: str, rows: list[list[Any]]) -> list[ImportRow]:
        out: list[ImportRow] = []
        occurrences: Counter[tuple] = Counter()
        for index, values in enumerate(rows, start=2):
            raw = {col: stringify(v) for col, v in zip(HEADER, values, strict=False)}
            row = ImportRow(file=file_name, line=index, raw=raw, status=RowStatus.NEW)
            out.append(row)
            try:
                self._parse_row(row, values)
            except (InvalidTickerError, ValueError, TypeError, ArithmeticError) as err:
                row.status, row.reason, row.candidate = RowStatus.ERROR, f"linha inválida: {err}", None
            if row.candidate is not None:
                c = row.candidate
                key = (
                    c.date,
                    c.ticker,
                    c.type,
                    c.quantity,
                    raw["Preço unitário"],
                    raw["Valor da Operação"],
                    c.broker,
                )
                occurrences[key] += 1
                row.dedup_hash = row_hash(self.name, *key, occurrences[key])
        return out

    def _parse_row(self, row: ImportRow, values: list[Any]) -> None:
        direction, day, kind, product, broker, qty, unit, value = values[:8]
        kind, product = str(kind).strip(), str(product).strip()
        if product.upper().startswith("FUTURO"):
            row.status, row.reason = RowStatus.IGNORED, "mercado futuro (fora da carteira)"
            return
        if product.upper().startswith(FIXED_INCOME_PREFIXES):
            row.status, row.reason = RowStatus.IGNORED, "renda fixa (fora do escopo)"
            return
        if kind in IGNORED:
            row.status, row.reason = RowStatus.IGNORED, IGNORED[kind]
            return
        tx_type = PROVENTS.get(kind) or EVENTS.get(kind)
        if tx_type is None:
            row.status, row.reason = RowStatus.ERROR, f"movimentação não reconhecida: {kind}"
            return

        code, _, name = product.partition(" - ")
        try:
            ticker = normalize_ticker(code)
        except InvalidTickerError:
            row.status, row.reason = RowStatus.IGNORED, f"produto fora do escopo: {product}"
            return

        on_date = to_date(day)
        quantity = to_decimal(qty) or Decimal(0)
        unit_price = to_decimal(unit)
        amount = to_decimal(value)
        candidate = Candidate(
            date=on_date,
            ticker=ticker,
            type=tx_type,
            quantity=quantity,
            broker=normalize_broker(str(broker)),
            asset_name=name.strip() or None,
        )
        if tx_type in PROVENTS.values():
            if amount is None:
                raise ValueError("provento sem valor")
            candidate.price = unit_price
            candidate.payment_date = on_date
            candidate.status = ProventStatus.CONFIRMED
            candidate.gross_amount, candidate.tax_withheld = _gross_and_tax(tx_type, on_date, amount)
        elif tx_type == T.FRACTION_AUCTION:
            if amount is None or not quantity:
                raise ValueError("leilão de fração sem quantidade ou valor")
            # Price = credited cash / quantity, so the realized result matches the money received
            candidate.price = amount / quantity
        elif tx_type in (T.SPLIT, T.REVERSE_SPLIT):
            candidate.credited_quantity = quantity
            candidate.quantity = Decimal(0)
        elif tx_type == T.BONUS:
            candidate.notes = "custo atribuído pendente (consultar aviso aos acionistas)"
        if str(direction).strip() != "Credito":
            raise ValueError(f"{kind} com sentido inesperado: {direction}")
        row.candidate = candidate


def _gross_and_tax(tx_type: TransactionType, payment_date, net: Decimal) -> tuple[Decimal, Decimal]:
    """The export's 'Valor da Operação' is the NET amount credited. For JCP the gross is rebuilt from the
    withholding rate in force on the payment date (the unit price in the file is rounded)."""
    rate = default_tax_table().rate(tx_type, payment_date)
    if not rate:
        return net, Decimal(0)
    gross = (net / (1 - rate)).quantize(CENT, rounding=ROUND_HALF_UP)
    return gross, gross - net
