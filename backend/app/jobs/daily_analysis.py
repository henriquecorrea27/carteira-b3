"""Daily job: run the rule engine for every stock in the portfolio and store today's decisions.

Run manually or from the OS scheduler:  uv run python -m app.jobs.daily_analysis [--profile ID]
"""

import argparse
import logging
import sys

from app.core.db import session_for
from app.corporate_events.b3_source import B3CorporateEventsSource
from app.jobs import add_profile_arg, profiles_for, tag
from app.market_data.yfinance_provider import YFinanceProvider
from app.rules.service import analyze_portfolio

log = logging.getLogger("app.jobs.daily_analysis")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.daily_analysis")
    add_profile_arg(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    failed = False
    for profile in profiles_for(args):
        with session_for(profile) as session:
            run = analyze_portfolio(session, YFinanceProvider(), B3CorporateEventsSource())
        log.info(
            "%sanalyzed: %s | skipped (no rules): %s",
            tag(profile),
            ", ".join(run.analyzed),
            ", ".join(run.skipped) or "-",
        )
        for error in run.errors:
            log.warning("%s%s", tag(profile), error)
        failed = failed or bool(run.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
