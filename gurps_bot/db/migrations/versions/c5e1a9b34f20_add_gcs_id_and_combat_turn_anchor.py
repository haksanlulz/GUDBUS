"""add gcs_id to characters and current_combatant_id turn anchor to combats

Revision ID: c5e1a9b34f20
Revises: ab603fc2203e
Create Date: 2026-06-06

Adds two nullable columns:
- characters.gcs_id — stable GCS character id so a renamed sheet re-imports in
  place instead of orphaning a duplicate.
- combats.current_combatant_id — identity anchor for the current turn so a
  roster change (e.g. a faster combatant joining mid-combat) does not silently
  re-point whose turn it is.

Both are nullable with no backfill: existing characters carry NULL gcs_id until
a re-import backfills it, and existing combats carry NULL current_combatant_id
until the next advance/previous turn sets it (the service layer falls back to
current_index in the meantime).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e1a9b34f20'
down_revision: Union[str, Sequence[str], None] = 'ab603fc2203e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gcs_id', sa.String(length=100), nullable=True))
        batch_op.create_index('ix_characters_gcs_id', ['gcs_id'], unique=False)

    with op.batch_alter_table('combats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('current_combatant_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('combats', schema=None) as batch_op:
        batch_op.drop_column('current_combatant_id')

    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_index('ix_characters_gcs_id')
        batch_op.drop_column('gcs_id')
