"""Learning (Phase 2): repository memory and durable learning jobs.

Adds ``learning_jobs`` (same state machine as ``ingestion_jobs``),
``memory_items`` (semantic memory), ``memory_skills`` (playbooks),
``repo_briefs`` (core memory per indexed commit) and the append-only
``memory_ledger``. Purely additive; ``proposed_rules`` is unchanged.

Revision ID: 0004_learning
Revises: 0003_chunk_descriptions
Create Date: 2026-10-30 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

import app.shared.base_model
import app.shared.vector_type
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004_learning'
down_revision: str | Sequence[str] | None = '0003_chunk_descriptions'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = sa.text("status IN ('queued', 'running')")


def _timestamps(updated: bool = True) -> list[sa.Column]:
    cols = [sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'),
                      nullable=False)]
    if updated:
        cols.append(sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'),
                              nullable=False))
    return cols


def _repository_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE')


def _memory_columns() -> list[sa.Column]:
    """Columns shared by memory_items and memory_skills."""
    return [
        sa.Column('scope', sa.JSON(), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('support', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('tier', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('learned_at_commit', sa.String(length=64), nullable=False),
        sa.Column('valid_from_commit', sa.String(length=64), nullable=True),
        sa.Column('invalidated_at_commit', sa.String(length=64), nullable=True),
        sa.Column('search_text', sa.Text(), nullable=True),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('learning_jobs',
    sa.Column('id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('repository_id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('commit_sha', sa.String(length=64), nullable=True),
    sa.Column('options', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('error_kind', sa.String(length=32), nullable=True),
    sa.Column('stats', sa.JSON(), nullable=True),
    sa.Column('worker_id', sa.String(length=128), nullable=True),
    *_timestamps(updated=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=True),
    _repository_fk(),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('learning_jobs', schema=None) as batch_op:
        batch_op.create_index('idx_learning_jobs_status_created', ['status', 'created_at'], unique=False)
        batch_op.create_index('uq_learning_jobs_active', ['repository_id'], unique=True,
                              postgresql_where=_ACTIVE, sqlite_where=_ACTIVE)

    op.create_table('memory_items',
    sa.Column('id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('repository_id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    *_memory_columns(),
    sa.Column('embedding', app.shared.vector_type.EmbeddingVector(768), nullable=True),
    sa.Column('embedding_model', sa.String(length=128), nullable=True),
    *_timestamps(),
    _repository_fk(),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('memory_items', schema=None) as batch_op:
        batch_op.create_index('uq_memory_items_repo_key', ['repository_id', 'key'], unique=True)
        batch_op.create_index('idx_memory_items_repo_status', ['repository_id', 'status'], unique=False)

    op.create_table('memory_skills',
    sa.Column('id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('repository_id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('resources', sa.JSON(), nullable=True),
    *_memory_columns(),
    *_timestamps(),
    _repository_fk(),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('memory_skills', schema=None) as batch_op:
        batch_op.create_index('uq_memory_skills_repo_name', ['repository_id', 'name'], unique=True)

    op.create_table('repo_briefs',
    sa.Column('id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('repository_id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('commit_sha', sa.String(length=64), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('sections', sa.JSON(), nullable=True),
    *_timestamps(updated=False),
    _repository_fk(),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('repo_briefs', schema=None) as batch_op:
        batch_op.create_index('uq_repo_briefs_repo_commit', ['repository_id', 'commit_sha'], unique=True)

    op.create_table('memory_ledger',
    sa.Column('id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('repository_id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('run_id', sa.String(length=64), nullable=False),
    sa.Column('target_type', sa.String(length=16), nullable=False),
    sa.Column('target_id', app.shared.base_model.GUID(), nullable=False),
    sa.Column('action', sa.String(length=16), nullable=False),
    sa.Column('actor', sa.String(length=64), nullable=False),
    sa.Column('before', sa.JSON(), nullable=True),
    sa.Column('after', sa.JSON(), nullable=True),
    *_timestamps(updated=False),
    _repository_fk(),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('memory_ledger', schema=None) as batch_op:
        batch_op.create_index('idx_memory_ledger_repo_created', ['repository_id', 'created_at'], unique=False)
        batch_op.create_index('idx_memory_ledger_run', ['run_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('memory_ledger', 'repo_briefs', 'memory_skills', 'memory_items'):
        op.drop_table(table)
    with op.batch_alter_table('learning_jobs', schema=None) as batch_op:
        batch_op.drop_index('uq_learning_jobs_active', postgresql_where=_ACTIVE, sqlite_where=_ACTIVE)
        batch_op.drop_index('idx_learning_jobs_status_created')
    op.drop_table('learning_jobs')
