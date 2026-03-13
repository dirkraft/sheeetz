"""add_sheet_is_favorite

Revision ID: b3f1c2d4e5a6
Revises: 840a2c5493f8
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1c2d4e5a6'
down_revision: Union[str, Sequence[str], None] = '840a2c5493f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sheets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_favorite', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sheets', schema=None) as batch_op:
        batch_op.drop_column('is_favorite')
