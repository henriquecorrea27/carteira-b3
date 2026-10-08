"""Decimal JSON types. Money and quantities travel as strings so the frontend never sees floats."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import PlainSerializer


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _plain(value: Decimal) -> str:
    # Up to 8 decimals, without trailing zeros or exponent notation
    text = format(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


Money = Annotated[Decimal, PlainSerializer(_money, return_type=str, when_used="json")]
Number = Annotated[Decimal, PlainSerializer(_plain, return_type=str, when_used="json")]
