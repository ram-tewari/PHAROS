"""add search_vector column

Revision ID: z1y2x3w4v5u6
Revises: j0k1l2m3n4o5
Create Date: 2025-12-15 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "z1y2x3w4v5u6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add search_vector column for PostgreSQL full-text search."""
    # Determine database type
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    # Only add search_vector for PostgreSQL (SQLite uses FTS5 virtual tables)
    if is_postgresql:
        # Add tsvector column for full-text search
        op.add_column(
            "resources",
            sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        )

        # Create GIN index for efficient full-text search
        op.create_index(
            "idx_resources_search_vector",
            "resources",
            ["search_vector"],
            postgresql_using="gin",
        )

        # Create trigger to automatically update search_vector
        op.execute("""
            CREATE OR REPLACE FUNCTION resources_search_vector_update() RETURNS trigger AS $$
            BEGIN
                NEW.search_vector := 
                    setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
                    setweight(to_tsvector('english', COALESCE(NEW.creator, '')), 'C') ||
                    setweight(to_tsvector('english', COALESCE(NEW.publisher, '')), 'D');
                RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
        """)

        op.execute("""
            CREATE TRIGGER resources_search_vector_trigger
            BEFORE INSERT OR UPDATE ON resources
            FOR EACH ROW
            EXECUTE FUNCTION resources_search_vector_update();
        """)

        # Update existing rows
        op.execute("""
            UPDATE resources SET search_vector = 
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(description, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(creator, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(publisher, '')), 'D');
        """)
    else:
        # For SQLite, add a nullable text column (not used, but keeps schema consistent)
        op.add_column("resources", sa.Column("search_vector", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove search_vector column."""
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    if is_postgresql:
        # Drop trigger and function
        op.execute(
            "DROP TRIGGER IF EXISTS resources_search_vector_trigger ON resources;"
        )
        op.execute("DROP FUNCTION IF EXISTS resources_search_vector_update();")

        # Drop index
        op.drop_index("idx_resources_search_vector", table_name="resources")

    # Drop column
    op.drop_column("resources", "search_vector")
