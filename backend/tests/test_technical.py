"""F8 — chart analysis: price vs. the 200-day SMA of the split-adjusted daily closes (CLAUDE.md §5.6)."""

from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.market_data.base import DailyBar
from app.models import PriceHistory
from app.rules import service as rules
from app.rules.engine import load_rules
from app.rules.technical import compute_technical, sma_score
from tests.test_rules import ingested  # noqa: F401 — fixture

CFG = load_rules()["technical"]


def closes(last: str, other: str) -> list[D]:
    """198 closes of 10, one `other` and the current price `last`: the SMA200 is 10 when other + last = 20."""
    return [D(10)] * 198 + [D(other), D(last)]


@pytest.mark.parametrize(
    ("last", "other", "distance", "score"),
    [
        ("10", "10", "0", 50.0),  # on the SMA: watch
        ("10.5", "9.5", "0.05", 25.0),  # 5% above
        ("11", "9", "0.1", 0.0),  # 10% above: expensive
        ("12", "8", "0.2", 0.0),  # beyond the limit: clamped
        ("9.5", "10.5", "-0.05", 75.0),  # 5% below
        ("9", "11", "-0.1", 100.0),  # 10% below: cheap
        ("8", "12", "-0.2", 100.0),  # beyond the limit: clamped
    ],
)
def test_score_is_linear_in_the_distance_to_the_sma(last, other, distance, score):
    t = compute_technical(closes(last, other), CFG)
    assert t.sma == D(10)
    assert t.distance == D(distance)
    assert (t.score, t.price, t.sessions) == (score, D(last), 200)


def test_only_the_last_200_closes_count():
    t = compute_technical([D(1000)] * 50 + closes("10.5", "9.5"), CFG)
    assert (t.sma, t.score) == (D(10), 25.0)


def test_short_history_is_not_scored():
    t = compute_technical([D(10)] * 199, CFG)
    assert (t.score, t.sma, t.distance) == (None, None, None)
    assert t.note == "só 199 pregões de histórico (a MM200 precisa de 200)"


def test_score_step_is_five_points_per_percent():
    assert sma_score(D("0.01"), D("-0.10"), D("0.10")) == 45.0
    assert sma_score(D("-0.03"), D("-0.10"), D("0.10")) == 65.0


def _store(session, ticker, start, rows):
    """rows: (raw close, split-adjusted close) per trading day."""
    for i, (raw, adjusted) in enumerate(rows):
        session.add(
            PriceHistory(
                ticker=ticker,
                date=start + timedelta(days=i),
                close=D(raw),
                close_adjusted=D(adjusted),
                volume=D(1000),
                open=D(raw),
                high=D(raw),
                low=D(raw),
                source="test",
            )
        )
    session.commit()


def test_sma_uses_split_adjusted_closes(session_factory):
    # 1:2 split in the middle: raw 20 before and 10 after; adjusted is 10 all along
    today = date(2026, 10, 8)
    start = today - timedelta(days=249)
    with session_factory() as session:
        _store(session, "XPTO3", start, [("20", "10")] * 100 + [("10", "10")] * 149 + [("9", "9")])
        t = rules.technical_for(session, "XPTO3", None, today, load_rules())
    # SMA = (199 × 10 + 9) / 200 = 9,995 → distance −9,95% → score 99,8
    assert t.sma == D("9.995")
    assert t.score == 99.8


def test_sync_rewrites_stale_adjusted_closes_and_bars_are_adjusted(session_factory):
    today = date(2026, 10, 8)
    day = today - timedelta(days=10)

    class SplitMarket:
        name = "fake"

        def daily_bars(self, tickers, start, end):
            # After a 1:2 split the provider adjusts the old close: raw 20 → adjusted 10
            return {"XPTO3": [DailyBar(day, D(20), D(10), D(1000), D(19), D(21), D(18))]}

    with session_factory() as session:
        _store(session, "XPTO3", day, [("20", "20")])  # cached before the split
        bars = rules.price_bars(session, "XPTO3", SplitMarket(), today)
        row = session.query(PriceHistory).filter_by(ticker="XPTO3").one()
    assert (row.close, row.close_adjusted) == (D(20), D(10))  # raw close kept for the ledger
    bar = bars[0]
    assert (bar.open, bar.high, bar.low, bar.close) == (D("9.5"), D("10.5"), D(9), D(10))
    assert bar.volume == D(2000)


def test_analysis_without_enough_history_uses_the_fundamentals_only(client, ingested):  # noqa: F811
    body = client.get("/api/analysis/CMIG4").json()
    assert body["technical_weight"] == 0
    t = body["technical"]
    assert (t["score"], t["sessions"], t["sma_days"]) == (None, 3, 200)
    assert t["note"] == "só 3 pregões de histórico (a MM200 precisa de 200)"
