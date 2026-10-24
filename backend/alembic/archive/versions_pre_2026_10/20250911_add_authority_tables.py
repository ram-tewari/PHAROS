"""add authority tables

Revision ID: 20250911_add_authority_tables
Revises: 20250910_add_fts_and_triggers
Create Date: 2025-09-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250911_add_authority_tables"
down_revision = "20250910_add_fts_and_triggers"
branch_labels = None
depends_on = None


def _json_type(bind):
    # For SQLite, use JSON if available, else TEXT; for Postgres use JSONB
    if bind.dialect.name == "postgresql":
        return sa.dialects.postgresql.JSONB
    return sa.JSON


def upgrade() -> None:
    bind = op.get_bind()
    json_type = _json_type(bind)

    op.create_table(
        "authority_subjects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canonical_form", sa.String(), nullable=False, unique=True),
        sa.Column(
            "variants", json_type, nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "authority_creators",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canonical_form", sa.String(), nullable=False, unique=True),
        sa.Column(
            "variants", json_type, nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "authority_publishers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canonical_form", sa.String(), nullable=False, unique=True),
        sa.Column(
            "variants", json_type, nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("authority_publishers")
    op.drop_table("authority_creators")
    op.drop_table("authority_subjects")
