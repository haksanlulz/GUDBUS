"""add campaign_settings (per-guild house rules)

Revision ID: b8e4d2a70f15
Revises: a7d3e9c1f2b4
Create Date: 2026-07-27

One row per guild, created lazily. Absence means "all defaults", so existing
guilds need no backfill and the migration cannot lose anything.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8e4d2a70f15"
down_revision = "a7d3e9c1f2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        # B360 Rule of 14: RAW is on, so the default keeps existing behaviour
        sa.Column(
            "rule_of_14", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", name="uq_campaign_settings_guild"),
    )
    op.create_index(
        "ix_campaign_settings_guild_id", "campaign_settings", ["guild_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_settings_guild_id", table_name="campaign_settings")
    op.drop_table("campaign_settings")
