"""add repositories table for github hybrid storage

Revision ID: 20260419_repositories
Revises: 
Create Date: 2026-04-19 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260419_repositories'
down_revision = None  # Will be set to latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create repositories table for GitHub hybrid storage."""
    op.create_table(
        'repositories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=False),
        sa.Column('total_files', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_lines', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    
    # Create indexes
    op.create_index('idx_repository_url', 'repositories', ['url'], unique=True)
    op.create_index('idx_repository_name', 'repositories', ['name'])
    op.create_index('idx_repository_created', 'repositories', ['created_at'])


def downgrade() -> None:
    """Drop repositories table."""
    op.drop_index('idx_repository_created', table_name='repositories')
    op.drop_index('idx_repository_name', table_name='repositories')
    op.drop_index('idx_repository_url', table_name='repositories')
    op.drop_table('repositories')
