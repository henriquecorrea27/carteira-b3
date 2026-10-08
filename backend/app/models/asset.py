from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    # AssetClass value; inferred from the ticker until confirmed by the user or an external source
    asset_class: Mapped[str] = mapped_column(String(10))
    class_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    sector: Mapped[str | None] = mapped_column(String(120))
    sector_override: Mapped[str | None] = mapped_column(String(120))
