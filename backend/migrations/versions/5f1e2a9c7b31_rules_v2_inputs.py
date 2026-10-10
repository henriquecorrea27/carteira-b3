"""rules v2 inputs: cash flow, issuer status, B3 dividends flag

Revision ID: 5f1e2a9c7b31
Revises: c3b0bd4cb0f5
Create Date: 2026-10-10 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5f1e2a9c7b31'
down_revision: Union[str, Sequence[str], None] = 'c3b0bd4cb0f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fundamental_periods', sa.Column('operating_cash_flow', sa.Numeric(precision=24, scale=8), nullable=True))
    op.add_column('fundamental_periods', sa.Column('capex', sa.Numeric(precision=24, scale=8), nullable=True))
    op.add_column('companies', sa.Column('issuer_status', sa.String(length=60), nullable=True))
    op.add_column('companies', sa.Column('b3_pays_dividends', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('companies', 'b3_pays_dividends')
    op.drop_column('companies', 'issuer_status')
    op.drop_column('fundamental_periods', 'capex')
    op.drop_column('fundamental_periods', 'operating_cash_flow')
