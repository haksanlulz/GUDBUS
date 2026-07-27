"""add combatants.parries_by_weapon (B376 per-weapon parry count)

Revision ID: c3f1a8b56d20
Revises: b8e4d2a70f15
Create Date: 2026-07-27

B376 scopes the cumulative parry penalty to "that weapon or hand", but the count
lived in a single integer, so a two-weapon fighter was penalised for parries
made with the other hand.

Additive: `parries_this_turn` is kept as the turn total. Existing rows get an
empty map, which reads as zero prior parries for every weapon — and since the
counters reset at the start of each turn anyway, a mid-combat upgrade loses at
most the current turn's per-weapon detail, never any durable state.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3f1a8b56d20"
down_revision = "b8e4d2a70f15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "combatants",
        sa.Column(
            "parries_by_weapon",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("combatants", "parries_by_weapon")
