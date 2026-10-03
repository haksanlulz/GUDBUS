"""crafting projects for every domain: state_json, and complexity goes nullable

Revision ID: b6c2d9e4f1a7
Revises: a3d9e5f71c08
Create Date: 2026-09-25

Two column changes on crafting_projects, no data rewrite:

- state_json (JSON, nullable) — a non-invention project's own figures, progress
  and result, in the shape its `services/crafting_<domain>.py` module owns.
  Invention projects leave it NULL and keep modifiers_json.
- complexity becomes nullable — it is B473's rating, which alchemy, enchantment,
  mundane crafting and repair do not have. Storing a domain-specific string in
  it would be a naming lie.

SQLite cannot relax NOT NULL in place, so batch mode rebuilds the table and
copies its rows; DEPLOY.md's "back up before an update that carries a data
migration" applies. Downgrade restores NOT NULL and so requires that no
non-invention project exist — it fails loudly otherwise rather than inventing
a complexity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6c2d9e4f1a7'
down_revision: Union[str, Sequence[str], None] = 'a3d9e5f71c08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('crafting_projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('state_json', sa.JSON(), nullable=True))
        batch_op.alter_column(
            'complexity', existing_type=sa.String(length=16), nullable=True
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('crafting_projects', schema=None) as batch_op:
        batch_op.alter_column(
            'complexity', existing_type=sa.String(length=16), nullable=False
        )
        batch_op.drop_column('state_json')
