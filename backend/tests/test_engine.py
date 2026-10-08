"""Closed numeric cases for the portfolio engine. Every expected value is computed by hand."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.portfolio.engine import LedgerEntry, LedgerError, build_portfolio, quantity_on
from app.portfolio.types import ProventStatus
from app.portfolio.types import TransactionType as T


def buy(day, ticker, qty, price, costs="0", seq=0):
    return LedgerEntry(day, ticker, T.BUY, D(qty), D(price), D(costs), seq=seq)


def sell(day, ticker, qty, price, costs="0", seq=0):
    return LedgerEntry(day, ticker, T.SELL, D(qty), D(price), D(costs), seq=seq)


class TestAveragePrice:
    def test_buys_include_costs_in_acquisition_cost(self):
        # (100 × 10 + 5) = 1005 → PM 10,05 ; + (50 × 13 + 2,50) = 1657,50 / 150 → PM 11,05
        result = build_portfolio(
            [
                buy(date(2024, 1, 2), "WEGE3", "100", "10", "5"),
                buy(date(2024, 2, 1), "WEGE3", "50", "13", "2.5"),
            ]
        )
        pos = result.position("WEGE3")
        assert pos.quantity == D("150")
        assert pos.total_cost == D("1657.5")
        assert pos.avg_price == D("11.05")

    def test_sell_keeps_pm_and_realizes_result(self):
        entries = [
            buy(date(2024, 1, 2), "WEGE3", "100", "10", "5"),
            buy(date(2024, 2, 1), "WEGE3", "50", "13", "2.5"),
            # proceeds 60 × 15 − 3 = 897 ; cost basis 60 × 11,05 = 663 ; result 234
            sell(date(2024, 3, 1), "WEGE3", "60", "15", "3"),
        ]
        result = build_portfolio(entries)
        pos = result.position("WEGE3")
        assert pos.quantity == D("90")
        assert pos.avg_price == D("11.05")
        assert pos.total_cost == D("994.5")
        assert pos.realized_result == D("234")
        sale = result.sales[0]
        assert (sale.proceeds, sale.cost_basis, sale.result) == (D("897"), D("663"), D("234"))

    def test_closing_position_zeroes_pm_and_rebuy_starts_fresh(self):
        entries = [
            buy(date(2024, 1, 2), "WEGE3", "100", "10", "5"),
            buy(date(2024, 2, 1), "WEGE3", "50", "13", "2.5"),
            sell(date(2024, 3, 1), "WEGE3", "60", "15", "3"),
            # proceeds 810 ; cost basis 994,50 ; result −184,50
            sell(date(2024, 4, 1), "WEGE3", "90", "9"),
        ]
        closed = build_portfolio(entries).position("WEGE3")
        assert closed.quantity == 0
        assert closed.total_cost == 0
        assert closed.avg_price == 0
        assert closed.realized_result == D("49.5")  # 234 − 184,50

        reopened = build_portfolio([*entries, buy(date(2024, 5, 1), "WEGE3", "10", "20")]).position("WEGE3")
        assert reopened.avg_price == D("20")
        assert reopened.realized_result == D("49.5")

    def test_partial_sell_with_repeating_decimal_pm(self):
        # PM = 100 / 3 ; sell 1 → cost basis 33,333… ; remaining 2 shares keep the same PM
        entries = [
            buy(date(2024, 1, 2), "ABCD3", "3", "33.3333333333", "0.0000000001"),
            sell(date(2024, 1, 3), "ABCD3", "1", "40"),
        ]
        pos = build_portfolio(entries).position("ABCD3")
        assert pos.quantity == D("2")
        assert pos.avg_price.quantize(D("0.01")) == D("33.33")
        assert pos.total_cost.quantize(D("0.01")) == D("66.67")

    def test_oversell_is_rejected(self):
        with pytest.raises(LedgerError) as err:
            build_portfolio(
                [buy(date(2024, 1, 2), "WEGE3", "10", "10"), sell(date(2024, 1, 3), "WEGE3", "11", "10")]
            )
        assert err.value.code == "INSUFFICIENT_POSITION"

    def test_sell_without_position_is_rejected(self):
        with pytest.raises(LedgerError):
            build_portfolio([sell(date(2024, 1, 3), "WEGE3", "1", "10")])

    def test_same_day_buy_runs_before_sell(self):
        # Sell entered first in the batch (seq 0) still applies after the buy of the same day
        entries = [
            sell(date(2024, 1, 2), "WEGE3", "5", "12", seq=0),
            buy(date(2024, 1, 2), "WEGE3", "10", "10", seq=1),
        ]
        pos = build_portfolio(entries).position("WEGE3")
        assert pos.quantity == D("5")
        assert pos.realized_result == D("10")  # 5 × (12 − 10)

    def test_entries_are_replayed_chronologically_regardless_of_input_order(self):
        entries = [sell(date(2024, 3, 1), "WEGE3", "50", "20"), buy(date(2024, 1, 2), "WEGE3", "100", "10")]
        assert build_portfolio(entries).position("WEGE3").realized_result == D("500")

    def test_zero_quantity_is_rejected(self):
        with pytest.raises(LedgerError):
            build_portfolio([buy(date(2024, 1, 2), "WEGE3", "0", "10")])


class TestCorporateEvents:
    def test_split_multiplies_quantity_and_divides_pm(self):
        # 100 × 30 = 3000 ; split 1:3 → 300 shares, PM 10
        entries = [
            buy(date(2024, 1, 2), "BBAS3", "100", "30"),
            LedgerEntry(date(2024, 4, 16), "BBAS3", T.SPLIT, factor=D("3")),
        ]
        pos = build_portfolio(entries).position("BBAS3")
        assert pos.quantity == D("300")
        assert pos.avg_price == D("10")
        assert pos.total_cost == D("3000")

    def test_trade_on_ex_date_is_already_post_split(self):
        entries = [
            buy(date(2024, 1, 2), "BBAS3", "100", "30"),
            sell(date(2024, 4, 16), "BBAS3", "250", "11"),  # only possible after the split
            LedgerEntry(date(2024, 4, 16), "BBAS3", T.SPLIT, factor=D("3")),
        ]
        pos = build_portfolio(entries).position("BBAS3")
        assert pos.quantity == D("50")
        assert pos.realized_result == D("250")  # 250 × (11 − 10)

    def test_reverse_split_with_fraction_auction(self):
        # 125 shares, PM 2 (cost 250) ; reverse split 10:1 → 12,5 shares, PM 20
        # fraction 0,5 auctioned at 18 → proceeds 9, cost basis 10, result −1 ; 12 shares, cost 240
        entries = [
            buy(date(2024, 1, 2), "MGLU3", "125", "2"),
            LedgerEntry(date(2024, 5, 28), "MGLU3", T.REVERSE_SPLIT, factor=D("10")),
        ]
        mid = build_portfolio(entries).position("MGLU3")
        assert mid.quantity == D("12.5")
        assert mid.avg_price == D("20")

        entries.append(LedgerEntry(date(2024, 6, 20), "MGLU3", T.FRACTION_AUCTION, D("0.5"), D("18")))
        pos = build_portfolio(entries).position("MGLU3")
        assert pos.quantity == D("12")
        assert pos.total_cost == D("240")
        assert pos.avg_price == D("20")
        assert pos.realized_result == D("-1")

    def test_bonus_with_attributed_cost_recalculates_pm(self):
        # 100 × 12 = 1200 ; bonus 10% → 10 shares at attributed cost 5,50 → 1255 / 110
        entries = [
            buy(date(2024, 1, 2), "ITSA4", "100", "12"),
            LedgerEntry(date(2024, 11, 29), "ITSA4", T.BONUS, D("10"), D("5.50")),
        ]
        pos = build_portfolio(entries).position("ITSA4")
        assert pos.quantity == D("110")
        assert pos.total_cost == D("1255")
        assert pos.avg_price.quantize(D("0.0001")) == D("11.4091")
        assert not pos.pending_bonus_cost

    def test_bonus_without_cost_is_flagged_pending(self):
        entries = [
            buy(date(2024, 1, 2), "ITSA4", "100", "12"),
            LedgerEntry(date(2024, 11, 29), "ITSA4", T.BONUS, D("10")),
        ]
        pos = build_portfolio(entries).position("ITSA4")
        assert pos.quantity == D("110")
        assert pos.total_cost == D("1200")
        assert pos.pending_bonus_cost

    def test_fractional_bonus_then_fraction_auction(self):
        # 100 shares PM 11 (1100) ; bonus 1 for 3 → 33,33 shares at cost 3 (99,99) → 133,33 / 1199,99
        # PM = 1199,99 / 133,33 = 9,000150… ; fraction 0,33 auctioned at 9 → proceeds 2,97
        # cost basis 0,33 × 9,000150 = 2,970050 ; result −0,000050 ; remaining cost 1197,019950
        entries = [
            buy(date(2025, 6, 2), "GOAU3", "100", "11"),
            LedgerEntry(date(2025, 12, 19), "GOAU3", T.BONUS, D("33.33"), D("3")),
            LedgerEntry(date(2026, 2, 24), "GOAU3", T.FRACTION_AUCTION, D("0.33"), D("9")),
        ]
        pos = build_portfolio(entries).position("GOAU3")
        assert pos.quantity == D("133")
        assert pos.total_cost.quantize(D("0.000001")) == D("1197.019950")
        assert pos.avg_price.quantize(D("0.000001")) == D("9.000150")
        assert pos.realized_result.quantize(D("0.000001")) == D("-0.000050")

    def test_bonus_without_position_is_rejected(self):
        with pytest.raises(LedgerError) as err:
            build_portfolio([LedgerEntry(date(2024, 11, 29), "ITSA4", T.BONUS, D("10"), D("5"))])
        assert err.value.code == "NO_POSITION"

    def test_split_without_position_is_ignored(self):
        result = build_portfolio([LedgerEntry(date(2024, 4, 16), "BBAS3", T.SPLIT, factor=D("2"))])
        assert result.position("BBAS3").quantity == 0

    def test_ticker_change_preserves_total_cost(self):
        # 100 × 10 = 1000 ; converts 2:1 into NEWC3 → 50 shares, PM 20
        entries = [
            buy(date(2024, 1, 2), "OLDC3", "100", "10"),
            LedgerEntry(date(2024, 6, 3), "OLDC3", T.TICKER_CHANGE, factor=D("0.5"), target_ticker="NEWC3"),
        ]
        result = build_portfolio(entries)
        assert result.position("OLDC3").quantity == 0
        new = result.position("NEWC3")
        assert new.quantity == D("50")
        assert new.total_cost == D("1000")
        assert new.avg_price == D("20")

    def test_ticker_change_merges_into_existing_position(self):
        entries = [
            buy(date(2024, 1, 2), "OLDC3", "100", "10"),
            buy(date(2024, 1, 2), "NEWC3", "10", "25"),
            LedgerEntry(date(2024, 6, 3), "OLDC3", T.TICKER_CHANGE, factor=D("0.5"), target_ticker="NEWC3"),
        ]
        new = build_portfolio(entries).position("NEWC3")
        assert new.quantity == D("60")
        assert new.total_cost == D("1250")


class TestProvents:
    def test_received_and_receivable_are_separated(self):
        entries = [
            buy(date(2025, 1, 2), "CMIG4", "100", "10"),
            LedgerEntry(
                date(2025, 3, 10),
                "CMIG4",
                T.JCP,
                D("100"),
                D("1"),
                gross_amount=D("100"),
                tax_withheld=D("15"),
                payment_date=date(2025, 6, 30),
                status=ProventStatus.PAID,
            ),
            LedgerEntry(
                date(2025, 3, 10),
                "CMIG4",
                T.DIVIDEND,
                D("100"),
                D("0.5"),
                payment_date=date(2025, 12, 30),
                status=ProventStatus.ANNOUNCED,
            ),
        ]
        pos = build_portfolio(entries).position("CMIG4")
        assert (pos.provents_gross, pos.provents_tax, pos.provents_net) == (D("100"), D("15"), D("85"))
        assert pos.provents_receivable_net == D("50")

    def test_provents_survive_closing_the_position(self):
        entries = [
            buy(date(2025, 1, 2), "CMIG4", "100", "10"),
            LedgerEntry(
                date(2025, 3, 10), "CMIG4", T.DIVIDEND, D("100"), D("0.3"), payment_date=date(2025, 4, 1)
            ),
            sell(date(2025, 5, 2), "CMIG4", "100", "10"),
        ]
        pos = build_portfolio(entries).position("CMIG4")
        assert pos.quantity == 0
        assert pos.provents_net == D("30")


class TestQuantityOn:
    def test_position_at_end_of_record_date(self):
        entries = [
            buy(date(2025, 3, 3), "TAEE4", "100", "11"),
            buy(date(2025, 3, 10), "TAEE4", "10", "11"),  # bought on the record date → counts
            sell(date(2025, 3, 11), "TAEE4", "110", "12"),  # sold the day after → still entitled
        ]
        assert quantity_on(entries, "TAEE4", date(2025, 3, 9)) == D("100")
        assert quantity_on(entries, "TAEE4", date(2025, 3, 10)) == D("110")
        assert quantity_on(entries, "TAEE4", date(2025, 3, 11)) == 0
        assert quantity_on(entries, "XXXX3", date(2025, 3, 11)) == 0
