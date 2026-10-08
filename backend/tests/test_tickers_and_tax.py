from datetime import date
from decimal import Decimal as D

import pytest

from app.portfolio.tax import default_tax_table
from app.portfolio.tickers import InvalidTickerError, infer_asset_class, normalize_ticker
from app.portfolio.types import AssetClass
from app.portfolio.types import TransactionType as T


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PETR4F", "PETR4"),
        (" itsa4 ", "ITSA4"),
        ("TAEE11", "TAEE11"),
        ("TAEE11F", "TAEE11"),
        ("AAPL34", "AAPL34"),
    ],
)
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["PETR", "WDOF25X", "", "PETR4FF", "Futuro - WINV25"])
def test_normalize_ticker_rejects_invalid(raw):
    with pytest.raises(InvalidTickerError):
        normalize_ticker(raw)


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("PETR4", AssetClass.STOCK),
        ("ITSA3", AssetClass.STOCK),
        ("HGLG11", AssetClass.FII),
        ("AAPL34", AssetClass.BDR),
    ],
)
def test_infer_asset_class(ticker, expected):
    assert infer_asset_class(ticker) == expected


class TestTaxTable:
    def test_jcp_rate_by_payment_date(self):
        table = default_tax_table()
        assert table.rate(T.JCP, date(2025, 12, 31)) == D("0.15")
        assert table.rate(T.JCP, date(2026, 1, 1)) == D("0.175")

    def test_jcp_withheld_rounds_to_cents(self):
        table = default_tax_table()
        assert table.withheld(T.JCP, date(2025, 6, 30), D("37.07")) == D("5.56")  # 5,5605
        assert table.withheld(T.JCP, date(2026, 6, 30), D("38.755")) == D("6.78")  # 6,782125

    def test_dividends_are_exempt_by_default(self):
        assert default_tax_table().withheld(T.DIVIDEND, date(2026, 6, 30), D("1000")) == D("0")
