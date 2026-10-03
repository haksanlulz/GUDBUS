"""add will to combatants for the knockdown & stunning roll

Revision ID: f4a2c1b9d3e7
Revises: d7b3f0a1c2e4
Create Date: 2026-07-07

Adds one column:
- combatants.will — the combatant's Will, so the major-wound knockdown & stunning
  roll (B420) uses the higher of HT or Will. NOT NULL with server_default 10 so
  existing combatant rows get a usable value without a backfill pass (SQLite cannot
  add a NOT NULL column to a populated table without a default). The ORM model
  carries a Python-side default of 10 for new rows; the service layer reads Will
  from a character's attributes (default 10 when absent).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a2c1b9d3e7'
down_revision: Union[str, Sequence[str], None] = 'd7b3f0a1c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('combatants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('will', sa.Integer(), nullable=False, server_default='10')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('combatants', schema=None) as batch_op:
        batch_op.drop_column('will')
