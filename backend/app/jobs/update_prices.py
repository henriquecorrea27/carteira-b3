"""Daily job: refresh quotes (yfinance), IBOV and CDI into the local cache.

Run manually or from the OS scheduler:  uv run python -m app.jobs.update_prices [--profile ID]
"""

import argparse
import logging
import sys

from app.core.db import session_for
from app.jobs import add_profile_arg, profiles_for, tag
from app.market_data.bcb import BCBRatesProvider
from app.market_data.service import refresh_all
from app.market_data.yfinance_provider import YFinanceProvider

log = logging.getLogger("app.jobs.update_prices")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.update_prices")
    add_profile_arg(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    failed = False
    for profile in profiles_for(args):
        with session_for(profile) as session:
            result = refresh_all(session, YFinanceProvider(), BCBRatesProvider())
        log.info(
            "%sprices: %s new rows, benchmarks: %s new rows",
            tag(profile),
            result.prices_inserted,
            result.benchmarks_inserted,
        )
        for error in result.errors:
            log.warning("%s%s", tag(profile), error)
        if result.tickers_without_data:
            log.warning("%sno quotes found for: %s", tag(profile), ", ".join(result.tickers_without_data))
        failed = failed or bool(result.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
