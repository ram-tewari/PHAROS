"""add authority timestamps

Revision ID: 20260108_add_authority_timestamps
Revises: 20260108_fix_user_boolean_columns
Create Date: 2026-01-08 06:58:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260108_add_authority_timestamps"
down_revision = "20260108_fix_user_boolean_columns"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite-compatible approach: Try to add columns, ignore if they exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # Check and add columns for authority_subjects
    if 'authority_subjects' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('authority_subjects')]
        if 'created_at' not in columns:
            op.add_column('authority_subjects', sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))
        if 'updated_at' not in columns:
            op.add_column('authority_subjects', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))
    
    # Check and add columns for authority_creators
    if 'authority_creators' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('authority_creators')]
        if 'created_at' not in columns:
            op.add_column('authority_creators', sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))
        if 'updated_at' not in columns:
            op.add_column('authority_creators', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))
    
    # Check and add columns for authority_publishers
    if 'authority_publishers' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('authority_publishers')]
        if 'created_at' not in columns:
            op.add_column('authority_publishers', sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))
        if 'updated_at' not in columns:
            op.add_column('authority_publishers', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))


def downgrade():
    # Remove the columns if they exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    if 'authority_subjects' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('authority_subjects')]
        if 'created_at' in columns:
            op.drop_column('authority_subjects', 'created_at')
        if 'updated_at' in columns:
            op.drop_column('authority_subjects', 'updated_at')
    
    if 'authority_creators' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('authority_creators')]
        if 'created_at' in columns:
            op.drop_column('authority_creators', 'created_at')
        if 'updated_at' in columns:
            op.drop_column('authority_creators', 'updated_at')
    
    if 'authority_publishers' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('authority_publishers')]
        if 'created_at' in columns:
            op.drop_column('authority_publishers', 'created_at')
        if 'updated_at' in columns:
            op.drop_column('authority_publishers', 'updated_at')
