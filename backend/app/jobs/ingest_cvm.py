"""Monthly job: download CVM open data (DFP, ITR, FCA, cadastro) and extract the fundamentals.

Run manually or from the OS scheduler:  uv run python -m app.jobs.ingest_cvm
"""

import logging
import sys
import time

from app.core.db import SessionLocal
from app.fundamentals.service import ingest

log = logging.getLogger("app.jobs.ingest_cvm")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    started = time.monotonic()
    with SessionLocal() as session:
        result = ingest(session)
    log.info(
        "companies: %s, tickers: %s, periods: %s in %.0fs",
        result.companies,
        result.tickers,
        result.periods,
        time.monotonic() - started,
    )
    for error in result.errors:
        log.warning(error)
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
