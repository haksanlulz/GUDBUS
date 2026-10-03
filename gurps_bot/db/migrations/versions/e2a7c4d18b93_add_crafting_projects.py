"""add crafting_projects + crafting_charges (B473-474 invention projects)

Revision ID: e2a7c4d18b93
Revises: c3f1a8b56d20
Create Date: 2026-08-09

Two new tables, no backfill: a project only exists once someone starts one, so
existing databases need nothing and the migration cannot lose anything.

⚠️ Written as a migration and NOT left to create_all, deliberately. On
2026-07-27 `bootstrap.main()` called `create_and_stamp()` unconditionally, so
create_all built `campaign_settings` behind Alembic's back and the migration
then collided with the table it was supposed to create — a production
crash-loop. Every prior migration had only added COLUMNS, which create_all
ignores, which is why the class had never surfaced before. This is the second
new-table migration since; `tests/test_bootstrap_new_table.py` is the standing
guard and `tests/test_crafting_migration.py` runs this revision on a database
stamped at the previous head.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2a7c4d18b93"
down_revision = "c3f1a8b56d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crafting_projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=True),
        sa.Column("character_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "domain", sa.String(length=32), nullable=False, server_default="invention"
        ),
        sa.Column("complexity", sa.String(length=16), nullable=False),
        sa.Column(
            "stage", sa.String(length=16), nullable=False, server_default="concept"
        ),
        sa.Column("skill", sa.Integer(), nullable=False),
        sa.Column("retail_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("modifiers_json", sa.JSON(), nullable=True),
        # GM-only: B473's flawed theory. Never rendered to a channel.
        sa.Column(
            "flawed_theory", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elapsed_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("major_bugs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minor_bugs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crafting_projects_discord_user_id",
        "crafting_projects",
        ["discord_user_id"],
    )
    # Guild-scoped, so `cleanup_guild_data` purges it and the index is what
    # keeps that purge cheap on a shared host.
    op.create_index(
        "ix_crafting_projects_guild_id", "crafting_projects", ["guild_id"]
    )

    op.create_table(
        "crafting_charges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        # Null for facilities and copies, which buy the right to roll and a
        # finished item rather than a roll. Required for attempts, enforced in
        # the service — an attempt with no outcome is money gone with no record.
        sa.Column("outcome", sa.String(length=24), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["crafting_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crafting_charges_project_id", "crafting_charges", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_crafting_charges_project_id", table_name="crafting_charges")
    op.drop_table("crafting_charges")
    op.drop_index("ix_crafting_projects_guild_id", table_name="crafting_projects")
    op.drop_index(
        "ix_crafting_projects_discord_user_id", table_name="crafting_projects"
    )
    op.drop_table("crafting_projects")
