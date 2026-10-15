"""Scheduled jobs, each runnable from the CLI. Every job runs for all profiles (one database each, see
app.core.profiles) unless --profile picks one."""

import argparse

from app.core.profiles import Profile, get_profiles, select_profiles


def add_profile_arg(parser: argparse.ArgumentParser) -> None:
    ids = ", ".join(p.id for p in get_profiles())
    parser.add_argument("--profile", help=f"roda só para este perfil ({ids}); padrão: todos")


def profiles_for(args: argparse.Namespace) -> list[Profile]:
    return select_profiles(args.profile)


def tag(profile: Profile) -> str:
    """Log prefix naming the profile when there is more than one."""
    return f"[{profile.id}] " if len(get_profiles()) > 1 else ""
