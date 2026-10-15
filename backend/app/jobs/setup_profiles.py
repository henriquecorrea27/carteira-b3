"""Creates the database of every profile listed in PROFILES (backend/.env) that does not exist yet,
applies the migrations to all of them and loads the CVM data into the new ones (from the files cached on
disk).

    uv run python -m app.jobs.setup_profiles

Creating a database needs the PostgreSQL superuser (POSTGRES_SUPERUSER_PASSWORD in backend/.env, the same
used in the installation); the new database belongs to the app user, like the first one.
"""

import logging
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, get_settings
from app.core.db import session_for
from app.core.profiles import Profile, get_profiles
from app.fundamentals.service import ingest

log = logging.getLogger("app.jobs.setup_profiles")
SUPERUSER = "postgres"


def _exists(profile: Profile) -> bool:
    primary = get_profiles()[0]
    engine = create_engine(primary.database_url)
    try:
        with engine.connect() as conn:
            query = text("SELECT 1 FROM pg_database WHERE datname = :name")
            return conn.scalar(query, {"name": profile.database}) is not None
    finally:
        engine.dispose()


def _create(profile: Profile) -> None:
    password = get_settings().postgres_superuser_password
    if not password:
        raise SystemExit("POSTGRES_SUPERUSER_PASSWORD vazio em backend/.env: necessário para criar o banco")
    url = make_url(profile.database_url)
    admin_url = url.set(username=SUPERUSER, password=password, database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            # Identifiers come from the validated profile id ([a-z0-9_]) and the app's own DATABASE_URL
            conn.execute(
                text(
                    f'CREATE DATABASE "{profile.database}" OWNER "{url.username}" '
                    "ENCODING 'UTF8' TEMPLATE template0"
                )
            )
    finally:
        engine.dispose()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    created = []
    for profile in get_profiles():
        if _exists(profile):
            log.info("profile %s (%s): database %s ok", profile.id, profile.name, profile.database)
            continue
        _create(profile)
        created.append(profile)
        log.info("profile %s (%s): database %s created", profile.id, profile.name, profile.database)

    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    logging.getLogger().setLevel(logging.INFO)  # alembic.ini logging config lowers it to WARNING
    log.info("migrations applied to every profile")

    for profile in created:
        log.info("profile %s: loading CVM data (cached files)…", profile.id)
        with session_for(profile) as session:
            result = ingest(session)
        log.info("profile %s: %s companies, %s tickers", profile.id, result.companies, result.tickers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
