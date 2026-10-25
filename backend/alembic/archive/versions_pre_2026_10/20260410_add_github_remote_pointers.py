"""add_github_remote_pointers_to_document_chunks

Phase 2 – Hybrid GitHub Storage Architecture.

Adds seven columns to document_chunks:
  is_remote        – BOOLEAN flag (code chunk vs inline PDF chunk)
  github_uri       – VARCHAR(2048) raw GitHub content URL
  branch_reference – VARCHAR(255) pinned commit SHA or branch name
  start_line       – INTEGER  start of symbol in the file (1-based)
  end_line         – INTEGER  end of symbol in the file (1-based)
  ast_node_type    – VARCHAR(64) AST node kind (function/class/method/module)
  symbol_name      – VARCHAR(512) fully-qualified symbol name
  semantic_summary – TEXT  signature + docstring used for embedding

Also relaxes the NOT-NULL constraint on document_chunks.content so that
code chunks can omit raw source (it lives on GitHub instead).

Revision ID: 20260410_github_remote_ptrs
Revises: 20260410_hnsw_indexes
Create Date: 2026-04-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from alembic import context as alembic_context

revision: str = "20260410_github_remote_ptrs"
down_revision: Union[str, Sequence[str], None] = "20260410_hnsw_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite() -> bool:
    """Return True when the migration is running against SQLite."""
    bind = op.get_bind()
    return bind.dialect.name == "sqlite"


def upgrade() -> None:
    # ── Relax NOT-NULL on content ─────────────────────────────────────────
    # Existing rows keep their content; new code chunks will have NULL.
    # SQLite does not support ALTER COLUMN; skip on SQLite (it already
    # stores NULL freely regardless of the column definition).
    if not _is_sqlite():
        op.alter_column(
            "document_chunks",
            "content",
            existing_type=sa.Text(),
            nullable=True,
        )

    # ── Add remote-pointer columns ────────────────────────────────────────
    # Boolean server_default: PostgreSQL uses 'false', SQLite uses '0'.
    bool_default = sa.text("0") if _is_sqlite() else sa.text("false")

    # column comments are PostgreSQL-only; omit for SQLite compatibility
    _col_kwargs = {} if _is_sqlite() else {}

    op.add_column(
        "document_chunks",
        sa.Column("is_remote", sa.Boolean(), nullable=False, server_default=bool_default),
    )
    op.add_column(
        "document_chunks",
        sa.Column("github_uri", sa.String(2048), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("branch_reference", sa.String(255), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("start_line", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("end_line", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("ast_node_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("symbol_name", sa.String(512), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("semantic_summary", sa.Text(), nullable=True),
    )

    # ── Indexes to support common query patterns ──────────────────────────
    op.create_index(
        "idx_chunks_is_remote",
        "document_chunks",
        ["is_remote"],
    )
    op.create_index(
        "idx_chunks_symbol_name",
        "document_chunks",
        ["symbol_name"],
    )
    op.create_index(
        "idx_chunks_ast_node_type",
        "document_chunks",
        ["ast_node_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_chunks_ast_node_type", table_name="document_chunks")
    op.drop_index("idx_chunks_symbol_name", table_name="document_chunks")
    op.drop_index("idx_chunks_is_remote", table_name="document_chunks")

    op.drop_column("document_chunks", "semantic_summary")
    op.drop_column("document_chunks", "symbol_name")
    op.drop_column("document_chunks", "ast_node_type")
    op.drop_column("document_chunks", "end_line")
    op.drop_column("document_chunks", "start_line")
    op.drop_column("document_chunks", "branch_reference")
    op.drop_column("document_chunks", "github_uri")
    op.drop_column("document_chunks", "is_remote")

    # Re-apply NOT-NULL — skip on SQLite (ALTER COLUMN unsupported).
    # In production (PostgreSQL): ensure no NULL content rows before downgrading.
    if not _is_sqlite():
        op.alter_column(
            "document_chunks",
            "content",
            existing_type=sa.Text(),
            nullable=False,
        )
