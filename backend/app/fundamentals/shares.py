"""Share counts per class.

Primary source: B3 listed-company data (numberCommonShares / numberPreferredShares, always in units).
CVM `composicao_capital` is only a fallback because it has no scale column and companies mix units
and thousands (PETR, BBAS, GOAU in units; ITSA, TAEE, CMIG in thousands — checked Oct/2026). The scale
is then inferred from the net income / EPS the company itself reports."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.fundamentals.cvm_parser import CapitalComposition

ZERO = Decimal(0)


@dataclass(frozen=True)
class ShareCount:
    on: Decimal
    pn: Decimal
    treasury_on: Decimal
    treasury_pn: Decimal
    source: str
    as_of: date | None

    @property
    def outstanding(self) -> Decimal:
        return self.on - self.treasury_on + self.pn - self.treasury_pn


def _num(text: str | None) -> Decimal:
    return Decimal((text or "0").replace(".", "").replace(",", ".") or "0")


def from_b3(payload: list[dict], previous: ShareCount | None, today: date) -> ShareCount | None:
    """B3 totals (units) + treasury shares from the CVM fallback already stored (CVM-only data)."""
    if not payload:
        return None
    company = payload[0]
    on, pn = _num(company.get("numberCommonShares")), _num(company.get("numberPreferredShares"))
    if on + pn <= 0:
        return None
    return ShareCount(
        on=on,
        pn=pn,
        treasury_on=previous.treasury_on if previous else ZERO,
        treasury_pn=previous.treasury_pn if previous else ZERO,
        source="B3",
        as_of=today,
    )


def from_cvm(capital: CapitalComposition, net_income: Decimal | None, eps: Decimal | None) -> ShareCount:
    scale = Decimal(1)
    if net_income and eps and eps != 0:
        implied = abs(net_income / eps)
        reported = capital.on + capital.pn
        if reported and abs(reported * 1000 - implied) < abs(reported - implied):
            scale = Decimal(1000)
    return ShareCount(
        on=capital.on * scale,
        pn=capital.pn * scale,
        treasury_on=capital.treasury_on * scale,
        treasury_pn=capital.treasury_pn * scale,
        source="CVM",
        as_of=capital.as_of,
    )
