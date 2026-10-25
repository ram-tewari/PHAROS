"""add_proposed_rules_table

Phase 6 – Self-Improving Feedback Loop.

Creates the proposed_rules table for storing LLM-extracted coding rules
that survive the 14-day temporal heuristic sieve.

Revision ID: a7f8e9d0c1b2
Revises: None (standalone migration)
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "a7f8e9d0c1b2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposed_rules",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        # Source provenance
        sa.Column("repository", sa.String(1024), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        # Raw diff
        sa.Column("diff_payload", sa.Text(), nullable=False),
        # LLM-extracted rule
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("rule_description", sa.Text(), nullable=False),
        sa.Column("rule_schema", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        # Review lifecycle
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )

    op.create_index("ix_proposed_rules_status", "proposed_rules", ["status"])
    op.create_index(
        "ix_proposed_rules_repo_sha",
        "proposed_rules",
        ["repository", "commit_sha"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposed_rules_repo_sha", table_name="proposed_rules")
    op.drop_index("ix_proposed_rules_status", table_name="proposed_rules")
    op.drop_table("proposed_rules")
