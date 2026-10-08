"""Daily job: run the rule engine for every stock in the portfolio and store today's decisions.

Run manually or from the OS scheduler:  uv run python -m app.jobs.daily_analysis
"""

import logging
import sys

from app.core.db import SessionLocal
from app.corporate_events.b3_source import B3CorporateEventsSource
from app.market_data.yfinance_provider import YFinanceProvider
from app.rules.service import analyze_portfolio

log = logging.getLogger("app.jobs.daily_analysis")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    with SessionLocal() as session:
        run = analyze_portfolio(session, YFinanceProvider(), B3CorporateEventsSource())
    log.info("analyzed: %s | skipped (no rules): %s", ", ".join(run.analyzed), ", ".join(run.skipped) or "-")
    for error in run.errors:
        log.warning(error)
    return 1 if run.errors else 0


if __name__ == "__main__":
    sys.exit(main())
