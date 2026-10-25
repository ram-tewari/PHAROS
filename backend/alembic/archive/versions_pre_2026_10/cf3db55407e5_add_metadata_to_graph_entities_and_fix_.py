"""Add metadata to graph_entities and fix read_status default

Revision ID: cf3db55407e5
Revises: 25c9c391cb35
Create Date: 2026-04-17 21:00:24.786109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf3db55407e5'
down_revision: Union[str, Sequence[str], None] = '25c9c391cb35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add entity_metadata column to graph_entities (if not exists)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('graph_entities')]
    
    if 'entity_metadata' not in columns:
        op.add_column('graph_entities', sa.Column('entity_metadata', sa.JSON(), nullable=True))
    
    # For SQLite, we can't alter column defaults directly
    # The model already has default='unread', so new inserts will work
    # For existing NULL values, we'll update them
    connection.execute(sa.text("UPDATE resources SET read_status = 'unread' WHERE read_status IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove entity_metadata column from graph_entities
    op.drop_column('graph_entities', 'entity_metadata')
