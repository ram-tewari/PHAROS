"""Chunk descriptions for contextual retrieval.

Adds ``chunk_descriptions``: an LLM-written description per (git blob SHA,
symbol), written on the owner's machine by ``pharos describe`` and folded into
the embedded summary by the indexer. Purely additive.

Revision ID: 0003_chunk_descriptions
Revises: 0002_codeintel
Create Date: 2026-10-30 03:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003_chunk_descriptions'
down_revision: str | Sequence[str] | None = '0002_codeintel'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('chunk_descriptions',
    sa.Column('content_sha', sa.String(length=64), nullable=False),
    sa.Column('symbol_name', sa.String(length=512), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('content_sha', 'symbol_name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('chunk_descriptions')
