"""Daily job: refresh quotes (yfinance), IBOV and CDI into the local cache.

Run manually or from the OS scheduler:  uv run python -m app.jobs.update_prices
"""

import logging
import sys

from app.core.db import SessionLocal
from app.market_data.bcb import BCBRatesProvider
from app.market_data.service import refresh_all
from app.market_data.yfinance_provider import YFinanceProvider

log = logging.getLogger("app.jobs.update_prices")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    with SessionLocal() as session:
        result = refresh_all(session, YFinanceProvider(), BCBRatesProvider())
    log.info(
        "prices: %s new rows, benchmarks: %s new rows", result.prices_inserted, result.benchmarks_inserted
    )
    for error in result.errors:
        log.warning(error)
    if result.tickers_without_data:
        log.warning("no quotes found for: %s", ", ".join(result.tickers_without_data))
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
