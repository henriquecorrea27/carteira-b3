"""Closed numeric cases for daily valuation and TWR (método de cotas)."""

from datetime import date
from decimal import Decimal as D

from app.portfolio.engine import LedgerEntry
from app.portfolio.performance import PriceBook, cdi_index, daily_series, period_return
from app.portfolio.types import ProventStatus
from app.portfolio.types import TransactionType as T


def d(day):
    return date(2025, 1, day)


def test_twr_ignores_contributions_and_withdrawals():
    entries = [
        LedgerEntry(d(1), "WEGE3", T.BUY, D("10"), D("10")),  # in 100
        LedgerEntry(d(3), "WEGE3", T.BUY, D("10"), D("12")),  # in 120
        LedgerEntry(d(4), "WEGE3", T.SELL, D("20"), D("13")),  # out 260
    ]
    prices = PriceBook({"WEGE3": {d(1): D("11"), d(2): D("12"), d(3): D("12.6"), d(4): D("13")}})
    points = daily_series(entries, prices, until=d(5))
    by_day = {p.date: p for p in points}
    # d1: 110/100 ; d2: 120/110 ; d3: 252/(120+120) ; d4: (0+260)/252 → 1,1 · 1,0909… · 1,05 · 1,0317… = 1,30
    assert by_day[d(1)].quota == D("1.1")
    assert by_day[d(2)].quota == D("1.2")
    assert by_day[d(3)].quota == D("1.26")
    assert by_day[d(4)].quota.quantize(D("0.0000001")) == D("1.3")
    assert by_day[d(5)].quota == by_day[d(4)].quota  # no position, quota frozen
    assert by_day[d(3)].market_value == D("252.0")
    assert by_day[d(3)].invested == D("220")
    assert (by_day[d(4)].inflow, by_day[d(4)].outflow) == (D("0"), D("260"))


def test_provents_count_as_return_and_weekends_carry_last_close():
    entries = [
        LedgerEntry(d(1), "TAEE4", T.BUY, D("10"), D("10")),
        LedgerEntry(
            d(1), "TAEE4", T.DIVIDEND, D("10"), D("0.5"), payment_date=d(3), status=ProventStatus.PAID
        ),
    ]
    prices = PriceBook({"TAEE4": {d(1): D("10")}})  # no quotes after day 1
    points = daily_series(entries, prices, until=d(3))
    assert [p.market_value for p in points] == [D("100"), D("100"), D("100")]
    assert points[-1].provents == D("5.0")
    assert points[-1].quota == D("1.05")


def test_announced_provents_are_not_return_yet():
    entries = [
        LedgerEntry(d(1), "TAEE4", T.BUY, D("10"), D("10")),
        LedgerEntry(
            d(1), "TAEE4", T.DIVIDEND, D("10"), D("0.5"), payment_date=d(2), status=ProventStatus.ANNOUNCED
        ),
    ]
    points = daily_series(entries, PriceBook({"TAEE4": {d(1): D("10")}}), until=d(2))
    assert points[-1].quota == D("1")


def test_missing_quotes_value_position_at_cost_and_are_reported():
    entries = [LedgerEntry(d(1), "NOQT3", T.BUY, D("10"), D("10"), D("1"))]
    (point,) = daily_series(entries, PriceBook({}), until=d(1))
    assert point.market_value == D("101")
    assert point.missing_prices == ("NOQT3",)


def test_split_keeps_value_continuous_with_raw_prices():
    # Raw closes: 20 before the 1:2 split, 10 after → value 200 on both days, zero return
    entries = [
        LedgerEntry(d(1), "BBAS3", T.BUY, D("10"), D("20")),
        LedgerEntry(d(2), "BBAS3", T.SPLIT, factor=D("2")),
    ]
    prices = PriceBook({"BBAS3": {d(1): D("20"), d(2): D("10")}})
    points = daily_series(entries, prices, until=d(2))
    assert [p.market_value for p in points] == [D("200"), D("200")]
    assert points[-1].quota == D("1")


def test_period_return_uses_the_quota_before_the_period():
    entries = [LedgerEntry(d(1), "WEGE3", T.BUY, D("10"), D("10"))]
    prices = PriceBook({"WEGE3": {d(1): D("10"), d(2): D("11"), d(3): D("12.1")}})
    points = daily_series(entries, prices, until=d(3))
    assert period_return(points, d(3)) == D("0.1")  # 12,1 / 11 − 1
    assert period_return(points, d(1)).quantize(D("0.0001")) == D("0.21")


def test_cdi_index_compounds_daily_rates():
    index = cdi_index([(d(2), D("1")), (d(1), D("1"))])
    assert index[d(1)] == D("1.01")
    assert index[d(2)] == D("1.0201")
