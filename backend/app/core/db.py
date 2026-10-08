from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

# Quantities can be fractional (bonus shares, fraction auctions); prices need sub-cent precision.
NUMERIC = Numeric(24, 8)


class Base(DeclarativeBase):
    type_annotation_map = {Decimal: NUMERIC}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
