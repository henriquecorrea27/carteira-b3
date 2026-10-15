"""Monthly job: download CVM open data (DFP, ITR, FCA, cadastro) and extract the fundamentals.
Each profile database gets its own copy; the downloaded files are cached on disk and shared.

Run manually or from the OS scheduler:  uv run python -m app.jobs.ingest_cvm [--profile ID]
"""

import argparse
import logging
import sys
import time

from app.core.db import session_for
from app.fundamentals.service import ingest
from app.jobs import add_profile_arg, profiles_for, tag

log = logging.getLogger("app.jobs.ingest_cvm")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.ingest_cvm")
    add_profile_arg(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    failed = False
    for profile in profiles_for(args):
        started = time.monotonic()
        with session_for(profile) as session:
            result = ingest(session)
        log.info(
            "%scompanies: %s, tickers: %s, periods: %s in %.0fs",
            tag(profile),
            result.companies,
            result.tickers,
            result.periods,
            time.monotonic() - started,
        )
        for error in result.errors:
            log.warning("%s%s", tag(profile), error)
        failed = failed or bool(result.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
