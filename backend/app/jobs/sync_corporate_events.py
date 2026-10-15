"""Daily job: fetch provents and corporate events from B3 and apply them to the ledger.

Run manually or from the OS scheduler:  uv run python -m app.jobs.sync_corporate_events [--profile ID]
"""

import argparse
import logging
import sys

from app.core.db import session_for
from app.corporate_events.b3_source import B3CorporateEventsSource
from app.corporate_events.service import sync
from app.jobs import add_profile_arg, profiles_for, tag

log = logging.getLogger("app.jobs.sync_corporate_events")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.sync_corporate_events")
    add_profile_arg(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    failed = False
    for profile in profiles_for(args):
        with session_for(profile) as session:
            result = sync(session, B3CorporateEventsSource())
        a = result.applied
        log.info(
            "%sissuers: %s, events: %s | created %s, updated %s, removed %s, enriched %s",
            tag(profile),
            result.issuers,
            result.events_seen,
            a.created,
            a.updated,
            a.removed,
            a.enriched,
        )
        for message in result.errors + a.skipped:
            log.warning("%s%s", tag(profile), message)
        failed = failed or bool(result.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
