"""yfinance adapter. B3 tickers use the `.SA` suffix.

yfinance's `Close` is split-adjusted (BBAS3 shows ~28 before its 2024 1:2 split, when it traded ~56).
The ledger keeps historical share counts, so the raw close is rebuilt by multiplying the adjusted close
by every split ratio that happened after that day."""

import logging
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf

from app.market_data.base import DailyBar, MarketDataError

log = logging.getLogger(__name__)


def _dec(value: float) -> Decimal:
    return Decimal(repr(float(value))).quantize(Decimal("0.00000001"))


def unadjust(adjusted: pd.Series, splits: pd.Series) -> pd.Series:
    """Raw close = adjusted close × product of split ratios with ex-date after that day."""
    raw = adjusted.copy()
    for ex_date, ratio in splits.items():
        if ratio and ratio > 0:
            raw[raw.index < ex_date] *= ratio
    return raw


class YFinanceProvider:
    name = "yfinance"

    def daily_bars(self, tickers: list[str], start: date, end: date) -> dict[str, list[DailyBar]]:
        """Unknown/delisted tickers (yfinance answers 404 and an empty frame) are just missing from the
        result; MarketDataError is raised only when every requested ticker failed with an exception."""
        out: dict[str, list[DailyBar]] = {}
        failures = 0
        for ticker in tickers:
            try:
                bars = self._ticker_bars(ticker, start, end)
            except Exception as err:  # one bad ticker must not stop the others
                failures += 1
                log.warning("yfinance failed for %s: %s", ticker, err)
                continue
            if bars:
                out[ticker] = bars
        if tickers and failures == len(tickers):
            raise MarketDataError("yfinance indisponível")
        return out

    def _ticker_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        handle = yf.Ticker(f"{ticker}.SA")
        hist = handle.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=True,
        )
        if hist.empty:
            return []
        hist.index = pd.DatetimeIndex([ts.date() for ts in hist.index])
        # Splits after `end` also affect the adjusted closes inside the window
        splits = handle.splits
        splits.index = pd.DatetimeIndex([ts.date() for ts in splits.index])
        raw = unadjust(hist["Close"], splits[splits.index > hist.index.min()])
        return [
            DailyBar(
                date=day.date(),
                close=_dec(raw[day]),
                close_adjusted=_dec(row["Close"]),
                volume=Decimal(int(row["Volume"])) if pd.notna(row["Volume"]) else None,
            )
            for day, row in hist.iterrows()
            if pd.notna(row["Close"])
        ]

    def index_closes(self, symbol: str, start: date, end: date) -> list[tuple[date, Decimal]]:
        hist = yf.Ticker(symbol).history(
            start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), auto_adjust=False
        )
        if hist.empty:
            raise MarketDataError(f"yfinance não retornou dados para {symbol}")
        return [(ts.date(), _dec(close)) for ts, close in hist["Close"].items() if pd.notna(close)]
