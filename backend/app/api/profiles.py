"""Profiles the UI can switch between (each one is a separate database, see app.core.profiles)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.profiles import get_profiles

router = APIRouter(tags=["profiles"])


class ProfileOut(BaseModel):
    id: str
    name: str
    primary: bool
    discord: bool  # Discord report and watchlist alert (first profile only)


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles():
    return [ProfileOut(id=p.id, name=p.name, primary=p.primary, discord=p.primary) for p in get_profiles()]
