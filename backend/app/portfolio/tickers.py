import re

from app.portfolio.types import AssetClass

_TICKER_RE = re.compile(r"^[A-Z0-9]{4}\d{1,2}$")
_FRACTIONAL_RE = re.compile(r"^([A-Z0-9]{4}\d{1,2})F$")
_BDR_SUFFIXES = ("32", "33", "34", "35", "39")


class InvalidTickerError(ValueError):
    pass


def normalize_ticker(raw: str) -> str:
    """Upper-case, trim and map the odd-lot ticker (PETR4F) to the standard one (PETR4)."""
    ticker = raw.strip().upper()
    if match := _FRACTIONAL_RE.match(ticker):
        ticker = match.group(1)
    if not _TICKER_RE.match(ticker):
        raise InvalidTickerError(f"ticker inválido: {raw!r}")
    return ticker


def infer_asset_class(ticker: str) -> AssetClass:
    """Best-effort guess from the ticker suffix. Suffix 11 is ambiguous (FII, ETF or unit),
    so the result must stay editable by the user and be refined by external sources."""
    if ticker.endswith(_BDR_SUFFIXES):
        return AssetClass.BDR
    if ticker.endswith("11"):
        return AssetClass.FII
    return AssetClass.STOCK
