import threading
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy import DateTime, Numeric, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.profiles import Profile, current_profile, primary_profile

# Quantities can be fractional (bonus shares, fraction auctions); prices need sub-cent precision.
NUMERIC = Numeric(24, 8)


class Base(DeclarativeBase):
    type_annotation_map = {Decimal: NUMERIC}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# One engine per profile database, created on first use
_makers: dict[str, sessionmaker[Session]] = {}
_makers_lock = threading.Lock()


def sessionmaker_for(profile: Profile) -> sessionmaker[Session]:
    with _makers_lock:
        maker = _makers.get(profile.id)
        if maker is None:
            engine = create_engine(profile.database_url, pool_pre_ping=True)
            maker = _makers[profile.id] = sessionmaker(bind=engine, expire_on_commit=False)
        return maker


def session_for(profile: Profile) -> Session:
    return sessionmaker_for(profile)()


SessionLocal = sessionmaker_for(primary_profile())
engine = SessionLocal.kw["bind"]


def get_session(profile: Annotated[Profile, Depends(current_profile)]) -> Iterator[Session]:
    """The database of the profile picked in the UI (X-Profile header)."""
    with session_for(profile) as session:
        yield session
