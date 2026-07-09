"""add uq_wealth_owner unique constraint to the wealth table

Revision ID: d7b3f0a1c2e4
Revises: c5e1a9b34f20
Create Date: 2026-06-07

The Wealth ORM model declares UniqueConstraint('discord_user_id',
'character_id', name='uq_wealth_owner'), and the service layer relies on it to
reject a duplicate per-character wallet created by a first-touch race. The
original ab603fc2203e migration created the `wealth` table without that
constraint, so a migration-bootstrapped DB (the documented `alembic upgrade
head` deploy path) never had it — create_all has it, the migration didn't.
This backfills the constraint so the migrated schema matches the model.

(SQLite still treats two NULL character_id rows as distinct, so this does not
cover the characterless/default wallet — get_wealth(...).limit(1) remains the
universal first-touch-race guard for that case.)
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd7b3f0a1c2e4'
down_revision: Union[str, Sequence[str], None] = 'c5e1a9b34f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Pre-dedup: a pre-constraint DB may already hold duplicate per-character
    # wallets from a first-touch race (the service tolerates them today). Building
    # the unique index over dirty data would fail the whole `alembic upgrade head`
    # mid-rebuild, so drop the duplicates first — keep the lowest id per
    # (user, character_id). NULL character_id rows are exempt (the default-wallet
    # case the constraint can't cover on SQLite anyway).
    op.execute(
        """
        DELETE FROM wealth
        WHERE character_id IS NOT NULL
          AND id NOT IN (
            SELECT MIN(id) FROM wealth
            WHERE character_id IS NOT NULL
            GROUP BY discord_user_id, character_id
          )
        """
    )

    with op.batch_alter_table('wealth', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_wealth_owner', ['discord_user_id', 'character_id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('wealth', schema=None) as batch_op:
        batch_op.drop_constraint('uq_wealth_owner', type_='unique')
