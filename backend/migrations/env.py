"""Migrations run on the database of every profile (app.core.profiles): `alembic upgrade head` upgrades all of
them; `-x profile=<id>` limits to one. Autogenerate compares against the first profile only."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (register models on Base.metadata)
from app.core.db import Base
from app.core.profiles import Profile, primary_profile, select_profiles

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _targets() -> list[Profile]:
    if getattr(config.cmd_opts, "autogenerate", False):
        return [primary_profile()]
    return select_profiles(context.get_x_argument(as_dictionary=True).get("profile"))


def run_migrations_offline() -> None:
    context.configure(url=primary_profile().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    for profile in _targets():
        connectable = create_engine(profile.database_url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
