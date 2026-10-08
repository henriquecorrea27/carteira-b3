"""Banco Central SGS API (free). Series 12 = CDI daily rate in % per day.
Response: [{"data": "25/09/2026", "valor": "0.050788"}, ...]. Daily series are limited to 10-year
windows per request, so long ranges are split."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx

from app.market_data.base import MarketDataError

SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados"
CDI_SERIES = 12
# The API caps daily series at 10-year windows and gets slow on long ones; 1-year windows are reliable
_MAX_WINDOW = timedelta(days=365)
_ATTEMPTS = 3


def parse_sgs(payload: list[dict]) -> list[tuple[date, Decimal]]:
    return [(datetime.strptime(item["data"], "%d/%m/%Y").date(), Decimal(item["valor"])) for item in payload]


class BCBRatesProvider:
    name = "bcb"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=60)

    def cdi_daily(self, start: date, end: date) -> list[tuple[date, Decimal]]:
        out: list[tuple[date, Decimal]] = []
        window_start = start
        while window_start <= end:
            window_end = min(end, window_start + _MAX_WINDOW)
            out.extend(self._fetch(CDI_SERIES, window_start, window_end))
            window_start = window_end + timedelta(days=1)
        return out

    def _fetch(self, series: int, start: date, end: date) -> list[tuple[date, Decimal]]:
        params = {"formato": "json", "dataInicial": f"{start:%d/%m/%Y}", "dataFinal": f"{end:%d/%m/%Y}"}
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                response = self._client.get(SGS_URL.format(series=series), params=params)
                break
            except httpx.HTTPError as err:
                if attempt == _ATTEMPTS:
                    raise MarketDataError(f"BCB indisponível: {err}") from err
        # SGS answers 404 when the window has no business days yet (e.g. today before publication)
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise MarketDataError(f"BCB respondeu {response.status_code}")
        return parse_sgs(response.json())
