"""Daily job: refresh prices, provents and decisions, then send the daily report to Discord, followed by the
watchlist alert (price vs. SMA200; its own channel when DISCORD_WATCHLIST_WEBHOOK_URL is set).

Scheduled by the Windows Task Scheduler (scripts/register_tasks.ps1) on business days after the close and at
logon. It only sends what is due: a report already sent is not repeated, and a missed day (computer off) is
sent at the next run, marked as late.

    uv run python -m app.jobs.daily_report              # scheduled run (catch-up, no duplicates)
    uv run python -m app.jobs.daily_report --dry-run    # print the report and the watchlist without sending
    uv run python -m app.jobs.daily_report --now        # send both now (test), outside the schedule
"""

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR
from app.core.db import SessionLocal
from app.corporate_events.b3_source import B3CorporateEventsSource
from app.corporate_events.service import sync
from app.market_data.bcb import BCBRatesProvider
from app.market_data.service import refresh_all
from app.market_data.yfinance_provider import YFinanceProvider
from app.notifications import service
from app.rules.service import analyze_portfolio

log = logging.getLogger("app.jobs.daily_report")
LOG_FILE = BACKEND_DIR / "data" / "logs" / "daily_report.log"


def refresh(session: Session) -> list[str]:
    """Same sequence as the "Atualizar preços" button. A failing step is logged and the report goes on
    with the cached data (the failure shows up under "Pendências")."""
    market, events = YFinanceProvider(), B3CorporateEventsSource()
    steps = [
        ("cotações", lambda: refresh_all(session, market, BCBRatesProvider()).errors),
        ("proventos", lambda: sync(session, events).errors),
        ("análise", lambda: analyze_portfolio(session, market, events).errors),
    ]
    errors: list[str] = []
    for name, step in steps:
        try:
            errors += [f"{name}: {e}" for e in step()]
        except Exception as err:  # noqa: BLE001 — the report must go out even without fresh data
            session.rollback()
            log.exception("refresh step %s failed", name)
            errors.append(f"{name}: {err}")
    return errors


def _setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.daily_report")
    parser.add_argument("--dry-run", action="store_true", help="mostra o relatório sem enviar")
    parser.add_argument("--now", action="store_true", help="envia agora, fora do agendamento (teste)")
    parser.add_argument("--force", action="store_true", help="reenvia mesmo se o relatório do dia já foi")
    parser.add_argument("--no-refresh", action="store_true", help="não atualiza cotações/proventos antes")
    args = parser.parse_args(argv)
    _setup_logging()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # emojis on the Windows console

    now = service.local_now()
    notifier, watch_notifier = service.get_notifier(), service.get_watchlist_notifier()
    market = YFinanceProvider()
    with SessionLocal() as session:
        if args.dry_run or args.now:
            if not args.no_refresh:
                for error in refresh(session):
                    log.warning(error)
            day = service.manual_day(now)
            if args.dry_run:
                print(service.compose(session, day, now)[1])
                if service.has_watchlist(session):
                    print("\n" + service.compose_watchlist(session, day, now, market)[1])
                return 0
            if notifier is None:
                log.error("DISCORD_WEBHOOK_URL não configurada em backend/.env")
                return 2
            dispatches = [service.send_report(session, notifier, day, now, service.MANUAL)]
            if service.has_watchlist(session):
                dispatches.append(
                    service.send_watchlist(session, watch_notifier, day, now, service.MANUAL, market)
                )
            for d in dispatches:
                log.info("manual %s for %s: %s %s", d.kind.lower(), day, d.status, d.error or "")
            return 0 if all(d.status == service.SENT for d in dispatches) else 1

        run = service.run_scheduled(
            session, notifier, now, refresh=None if args.no_refresh else refresh, force=args.force
        )
        watch = service.run_scheduled(
            session, watch_notifier, now, force=args.force, kind=service.WATCHLIST, market=market
        )
    for error in run.refresh_errors:
        log.warning(error)
    if run.status == "NOT_CONFIGURED":
        log.warning("DISCORD_WEBHOOK_URL não configurada em backend/.env — relatório não enviado")
        return 0
    for name, r in (("report", run), ("watchlist", watch)):
        log.info("%s for %s: %s%s %s", name, r.day, r.status, " (late)" if r.late else "", r.error or "")
    return 1 if service.FAILED in (run.status, watch.status) else 0


if __name__ == "__main__":
    sys.exit(main())
