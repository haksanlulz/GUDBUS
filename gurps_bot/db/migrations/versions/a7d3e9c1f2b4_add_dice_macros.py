"""add dice_macros table for saved named dice expressions

Revision ID: a7d3e9c1f2b4
Revises: f4a2c1b9d3e7
Create Date: 2026-07-07

Creates the dice_macros table: a per-user store of named dice expressions
(e.g. 'greatsword' -> '2d+4'), unique per (discord_user_id, name). Names are
stored lowercased by the service so the unique constraint is case-insensitive.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3e9c1f2b4'
down_revision: Union[str, Sequence[str], None] = 'f4a2c1b9d3e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'dice_macros',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('discord_user_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('expression', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('discord_user_id', 'name', name='uq_macro_user_name'),
    )
    with op.batch_alter_table('dice_macros', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_dice_macros_discord_user_id'),
            ['discord_user_id'], unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('dice_macros', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dice_macros_discord_user_id'))
    op.drop_table('dice_macros')
