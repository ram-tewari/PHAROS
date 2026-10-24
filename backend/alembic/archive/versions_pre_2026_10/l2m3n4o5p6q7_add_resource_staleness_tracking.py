"""add resource staleness tracking

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-04-27 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, Sequence[str], None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_stale, last_indexed_sha, last_indexed_at columns to resources."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("resources")}

    if "is_stale" not in existing_cols:
        op.add_column(
            "resources",
            sa.Column(
                "is_stale",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.create_index(
            "ix_resources_is_stale",
            "resources",
            ["is_stale"],
            unique=False,
        )

    if "last_indexed_sha" not in existing_cols:
        op.add_column(
            "resources",
            sa.Column("last_indexed_sha", sa.String(length=64), nullable=True),
        )

    if "last_indexed_at" not in existing_cols:
        op.add_column(
            "resources",
            sa.Column(
                "last_indexed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    """Remove resource staleness tracking columns."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("resources")}
    existing_indexes = {i["name"] for i in inspector.get_indexes("resources")}

    if "ix_resources_is_stale" in existing_indexes:
        op.drop_index("ix_resources_is_stale", table_name="resources")

    for col in ("last_indexed_at", "last_indexed_sha", "is_stale"):
        if col in existing_cols:
            op.drop_column("resources", col)
