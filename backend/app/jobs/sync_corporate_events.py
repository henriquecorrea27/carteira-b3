"""Daily job: fetch provents and corporate events from B3 and apply them to the ledger.

Run manually or from the OS scheduler:  uv run python -m app.jobs.sync_corporate_events
"""

import logging
import sys

from app.core.db import SessionLocal
from app.corporate_events.b3_source import B3CorporateEventsSource
from app.corporate_events.service import sync

log = logging.getLogger("app.jobs.sync_corporate_events")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    with SessionLocal() as session:
        result = sync(session, B3CorporateEventsSource())
    a = result.applied
    log.info(
        "issuers: %s, events: %s | created %s, updated %s, removed %s, enriched %s",
        result.issuers,
        result.events_seen,
        a.created,
        a.updated,
        a.removed,
        a.enriched,
    )
    for message in result.errors + a.skipped:
        log.warning(message)
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
