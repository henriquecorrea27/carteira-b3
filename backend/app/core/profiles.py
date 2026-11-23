"""Profiles: independent portfolios on the same computer, each in its OWN PostgreSQL database (CLAUDE.md §1).
Nothing is shared between them (ledger, provents, decisions, watchlist, dispatch log), so one portfolio can
never show up in another. Market and CVM data are fetched again per database (the CVM files stay cached on
disk for all of them).

    PROFILES=eu:Eu,familiar:Familiar     # in backend/.env; empty → a single profile (the app as before)

The first profile uses DATABASE_URL; each other one the same server and credentials with the database name
suffixed by its id (carteira → carteira_familiar). Discord notifications are sent for the first profile only.
The UI picks the profile per request with the X-Profile header (absent → the first one)."""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated

from fastapi import Header, HTTPException, status
from sqlalchemy.engine import make_url

from app.core.config import get_settings

_ID = re.compile(r"^[a-z][a-z0-9_]{0,19}$")


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    database_url: str = field(repr=False)  # carries the password: never in logs
    primary: bool

    @property
    def database(self) -> str:
        return make_url(self.database_url).database or ""


class ProfileConfigError(ValueError):
    pass


class UnknownProfileError(LookupError):
    pass


def parse_profiles(spec: str, database_url: str, test_database_url: str | None = None) -> list[Profile]:
    entries = [part.strip() for part in spec.split(",") if part.strip()]
    if not entries:
        return [Profile("principal", "Minha carteira", database_url, True)]
    base = make_url(database_url)
    reserved = {base.database, make_url(test_database_url).database if test_database_url else None}
    profiles: list[Profile] = []
    for index, entry in enumerate(entries):
        pid, _, name = entry.partition(":")
        pid = pid.strip().lower()
        if not _ID.match(pid):
            raise ProfileConfigError(
                f"PROFILES: id inválido {pid!r} (letras minúsculas, números e _, começando por letra)"
            )
        if any(p.id == pid for p in profiles):
            raise ProfileConfigError(f"PROFILES: id repetido {pid!r}")
        if index == 0:
            url = database_url
        else:
            database = f"{base.database}_{pid}"
            if database in reserved:
                raise ProfileConfigError(
                    f"PROFILES: o perfil {pid!r} usaria o banco {database}, que é reservado"
                )
            url = base.set(database=database).render_as_string(hide_password=False)
        profiles.append(Profile(pid, name.strip() or pid.capitalize(), url, index == 0))
    return profiles


@lru_cache
def get_profiles() -> tuple[Profile, ...]:
    settings = get_settings()
    return tuple(parse_profiles(settings.profiles, settings.database_url, settings.database_url_test))


def primary_profile() -> Profile:
    return get_profiles()[0]


def find_profile(profile_id: str | None) -> Profile:
    if not profile_id:
        return primary_profile()
    for profile in get_profiles():
        if profile.id == profile_id.strip().lower():
            return profile
    raise UnknownProfileError(profile_id)


def select_profiles(profile_id: str | None) -> list[Profile]:
    """Jobs: every profile, or only the one given with --profile."""
    return [find_profile(profile_id)] if profile_id else list(get_profiles())


def current_profile(x_profile: Annotated[str | None, Header()] = None) -> Profile:
    """FastAPI dependency: the profile chosen in the UI (X-Profile header)."""
    try:
        return find_profile(x_profile)
    except UnknownProfileError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Perfil desconhecido: {x_profile}") from err
