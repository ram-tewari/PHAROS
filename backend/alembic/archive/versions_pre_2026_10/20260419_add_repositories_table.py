"""add repositories table for github hybrid storage

Revision ID: 20260419_repositories
Revises: 25c9c391cb35
Create Date: 2026-04-19 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260419_repositories'
down_revision = '25c9c391cb35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create repositories table for GitHub hybrid storage."""
    # Check if table already exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    if 'repositories' not in tables:
        # Use JSON for SQLite compatibility, JSONB for PostgreSQL
        metadata_type = postgresql.JSONB if connection.dialect.name == 'postgresql' else sa.JSON
        
        op.create_table(
            'repositories',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('url', sa.String(2048), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('metadata', metadata_type, nullable=False),
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
    # Check if table exists before dropping
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    if 'repositories' in tables:
        # Check if indexes exist before dropping
        indexes = [idx['name'] for idx in inspector.get_indexes('repositories')]
        
        if 'idx_repository_created' in indexes:
            op.drop_index('idx_repository_created', table_name='repositories')
        if 'idx_repository_name' in indexes:
            op.drop_index('idx_repository_name', table_name='repositories')
        if 'idx_repository_url' in indexes:
            op.drop_index('idx_repository_url', table_name='repositories')
        
        op.drop_table('repositories')
