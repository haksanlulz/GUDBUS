"""one default wallet per user: partial unique index on wealth

Revision ID: a3d9e5f71c08
Revises: e2a7c4d18b93
Create Date: 2026-09-25

uq_wealth_owner (d7b3f0a1c2e4) covers per-character wallets only, because
SQLite treats two NULL character_ids as distinct. So a first-touch race on
the DEFAULT wallet could leave two rows, and get_wealth reads only the oldest
— the other row's money was invisible. This adds a partial unique index over
discord_user_id WHERE character_id IS NULL.

Existing duplicates are folded first, not dropped: the extra rows hold money
real commands wrote. Each user's default rows collapse into the lowest id,
with the balances summed; that row's Status is kept.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3d9e5f71c08'
down_revision: Union[str, Sequence[str], None] = 'e2a7c4d18b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE wealth
        SET balance = (
            SELECT SUM(w2.balance) FROM wealth AS w2
            WHERE w2.discord_user_id = wealth.discord_user_id
              AND w2.character_id IS NULL
        )
        WHERE character_id IS NULL
          AND id IN (
            SELECT MIN(id) FROM wealth
            WHERE character_id IS NULL
            GROUP BY discord_user_id
            HAVING COUNT(*) > 1
          )
        """
    )
    op.execute(
        """
        DELETE FROM wealth
        WHERE character_id IS NULL
          AND id NOT IN (
            SELECT MIN(id) FROM wealth
            WHERE character_id IS NULL
            GROUP BY discord_user_id
          )
        """
    )
    op.create_index(
        'uq_wealth_default',
        'wealth',
        ['discord_user_id'],
        unique=True,
        sqlite_where=sa.text('character_id IS NULL'),
        postgresql_where=sa.text('character_id IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_wealth_default', table_name='wealth')
