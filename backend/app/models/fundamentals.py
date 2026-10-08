import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class Company(TimestampMixin, Base):
    """Listed company from the CVM registry (cadastro) enriched with share counts."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(18), unique=True)
    cd_cvm: Mapped[str | None] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(200))
    sector_cvm: Mapped[str | None] = mapped_column(String(120))
    # INDUSTRIAL (regular statements, also insurers) | BANK (financial-institution template)
    template: Mapped[str | None] = mapped_column(String(12))
    shares_on: Mapped[Decimal | None]
    shares_pn: Mapped[Decimal | None]
    treasury_on: Mapped[Decimal | None]
    treasury_pn: Mapped[Decimal | None]
    shares_source: Mapped[str | None] = mapped_column(String(20))
    shares_as_of: Mapped[dt.date | None] = mapped_column(Date)


class CompanyTicker(Base):
    """Ticker ↔ CNPJ from the CVM FCA (valor mobiliário)."""

    __tablename__ = "company_tickers"

    ticker: Mapped[str] = mapped_column(String(12), primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(18), ForeignKey("companies.cnpj"), index=True)
    share_class: Mapped[str] = mapped_column(String(6))  # ON | PN | UNIT
    unit_composition: Mapped[str | None] = mapped_column(String(40))


class FundamentalPeriod(TimestampMixin, Base):
    """Key figures extracted from one DFP/ITR (latest version), in R$ units.

    Flows (revenue … dividends_paid) cover the fiscal year (DFP) or the year-to-date (ITR).
    `comparative` rows come from the prior-year columns of a newer document (only flows), and are
    replaced when the original document is ingested."""

    __tablename__ = "fundamental_periods"
    __table_args__ = (UniqueConstraint("cnpj", "doc_type", "period_end"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(18), index=True)
    doc_type: Mapped[str] = mapped_column(String(4))  # DFP | ITR
    period_start: Mapped[dt.date | None] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer)
    received_on: Mapped[dt.date | None] = mapped_column(Date)
    consolidated: Mapped[bool] = mapped_column(Boolean)
    comparative: Mapped[bool] = mapped_column(Boolean, default=False)
    template: Mapped[str] = mapped_column(String(12))

    revenue: Mapped[Decimal | None]
    ebit: Mapped[Decimal | None]
    net_income: Mapped[Decimal | None]
    net_income_controlling: Mapped[Decimal | None]
    d_and_a: Mapped[Decimal | None]
    dividends_paid: Mapped[Decimal | None]

    total_assets: Mapped[Decimal | None]
    current_assets: Mapped[Decimal | None]
    current_liabilities: Mapped[Decimal | None]
    cash: Mapped[Decimal | None]
    gross_debt: Mapped[Decimal | None]  # loans + debentures, IFRS 16 leases excluded
    leases: Mapped[Decimal | None]
    equity: Mapped[Decimal | None]
    equity_controlling: Mapped[Decimal | None]
    eps: Mapped[Decimal | None]

    # Accounts that could not be located (e.g. D&A without a standard code)
    missing: Mapped[str | None] = mapped_column(Text)
