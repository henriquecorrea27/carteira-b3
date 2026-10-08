from bisect import bisect_right
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import RULES_CONFIG_DIR
from app.portfolio.types import TransactionType

CENT = Decimal("0.01")

_TYPE_KEYS = {
    TransactionType.JCP: "jcp",
    TransactionType.DIVIDEND: "dividend",
    TransactionType.INCOME: "income",
}


class TaxTable:
    def __init__(self, schedules: dict[str, list[tuple[date, Decimal]]]):
        self._schedules = {key: sorted(entries) for key, entries in schedules.items()}

    @classmethod
    def from_yaml(cls, path: Path) -> "TaxTable":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            {
                key: [(entry["valid_from"], Decimal(str(entry["rate"]))) for entry in entries]
                for key, entries in raw.items()
            }
        )

    def rate(self, provent_type: TransactionType, payment_date: date) -> Decimal:
        entries = self._schedules[_TYPE_KEYS[provent_type]]
        idx = bisect_right([valid_from for valid_from, _ in entries], payment_date) - 1
        if idx < 0:
            raise ValueError(f"no {provent_type} tax rate configured for {payment_date}")
        return entries[idx][1]

    def withheld(self, provent_type: TransactionType, payment_date: date, gross: Decimal) -> Decimal:
        return (gross * self.rate(provent_type, payment_date)).quantize(CENT, rounding=ROUND_HALF_UP)


@lru_cache
def default_tax_table() -> TaxTable:
    return TaxTable.from_yaml(RULES_CONFIG_DIR / "tax_rates.yaml")
