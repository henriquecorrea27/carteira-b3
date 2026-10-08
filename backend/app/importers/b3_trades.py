"""B3 Área do Investidor — 'Negociação' export → BUY/SELL.
Layout documented in tests/fixtures/b3/README.md (validated against real files)."""

from collections import Counter
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
from app.portfolio.tickers import InvalidTickerError, normalize_ticker
from app.portfolio.types import TransactionType

HEADER = [
    "Data do Negócio",
    "Tipo de Movimentação",
    "Mercado",
    "Prazo/Vencimento",
    "Instituição",
    "Código de Negociação",
    "Quantidade",
    "Preço",
    "Valor",
]
SIDES = {"Compra": TransactionType.BUY, "Venda": TransactionType.SELL}
EQUITY_MARKETS = {"Mercado à Vista", "Mercado Fracionário"}


class B3TradesImporter:
    name = "b3_negociacao"

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
                trade_date, side, market, _due, broker, code, qty, price, _value = values[:9]
                market = str(market).strip()
                if market == "Futuro":
                    row.status, row.reason = RowStatus.IGNORED, "mercado futuro (fora da carteira)"
                    continue
                if market not in EQUITY_MARKETS:
                    row.status, row.reason = RowStatus.IGNORED, f"mercado não suportado: {market}"
                    continue
                tx_type = SIDES.get(str(side).strip())
                if tx_type is None:
                    row.status, row.reason = RowStatus.ERROR, f"tipo de movimentação desconhecido: {side}"
                    continue
                candidate = Candidate(
                    date=to_date(trade_date),
                    ticker=normalize_ticker(str(code)),
                    type=tx_type,
                    quantity=to_decimal(qty),
                    price=to_decimal(price),
                    broker=normalize_broker(str(broker)),
                )
            except (InvalidTickerError, ValueError, TypeError, ArithmeticError) as err:
                row.status, row.reason = RowStatus.ERROR, f"linha inválida: {err}"
                continue
            key = (
                candidate.date,
                candidate.ticker,
                candidate.type,
                candidate.quantity,
                candidate.price,
                candidate.broker,
            )
            occurrences[key] += 1
            # Identical trades on the same day are legitimate: the occurrence index keeps them apart
            row.dedup_hash = row_hash(self.name, *key, occurrences[key])
            row.candidate = candidate
        return out
