"""add_sheet_last_opened_at

Revision ID: c1d2e3f4a5b6
Revises: b3f1c2d4e5a6
Create Date: 2026-03-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b3f1c2d4e5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sheets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_opened_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sheets', schema=None) as batch_op:
        batch_op.drop_column('last_opened_at')
