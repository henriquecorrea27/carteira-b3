"""Chart analysis (F8): the 200-day simple moving average as a PRICE reference (cheap or expensive), not as an
entry signal. Pure: receives the split-adjusted daily closes, returns the technical score 0–100.

distance = price / SMA − 1. Score is linear between the `cheap` distance (100) and the `expensive` one (0),
clamped: with ±10%, 10% below the SMA = 100, on the SMA = 50, 10% above = 0 (CLAUDE.md §5.6)."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Technical:
    score: float | None  # None → not computed (the price score uses the fundamentals only)
    sma: Decimal | None
    distance: Decimal | None  # fraction: 0.05 = price 5% above the SMA
    price: Decimal | None  # last close of the series
    sessions: int  # closes available
    sma_days: int
    cheap: Decimal  # distance that scores 100
    expensive: Decimal  # distance that scores 0
    note: str | None = None


def sma_score(distance: Decimal, cheap: Decimal, expensive: Decimal) -> float:
    ratio = (expensive - distance) / (expensive - cheap)
    return round(float(min(max(ratio, Decimal(0)), Decimal(1))) * 100, 1)


def compute_technical(closes: Sequence[Decimal], cfg: dict) -> Technical:
    """`closes`: split-adjusted daily closes, oldest first, the last one being the current price."""
    days = int(cfg["sma_days"])
    cheap, expensive = Decimal(str(cfg["cheap"])), Decimal(str(cfg["expensive"]))
    base = {"sessions": len(closes), "sma_days": days, "cheap": cheap, "expensive": expensive}
    price = closes[-1] if closes else None
    if len(closes) < days:
        note = f"só {len(closes)} pregões de histórico (a MM{days} precisa de {days})"
        return Technical(None, None, None, price, note=note, **base)
    sma = sum(closes[-days:], Decimal(0)) / days
    distance = price / sma - 1
    return Technical(sma_score(distance, cheap, expensive), sma, distance, price, **base)
