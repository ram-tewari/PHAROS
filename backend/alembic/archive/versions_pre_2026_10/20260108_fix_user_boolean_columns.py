"""fix user boolean columns

Revision ID: 20260108_fix_user_boolean_columns
Revises: 20260108_fix_boolean_columns
Create Date: 2026-01-08 03:50:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260108_fix_user_boolean_columns"
down_revision = "20260108_fix_boolean_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Convert User and ModelVersion boolean columns from INTEGER to BOOLEAN."""
    # Get connection to check database type
    conn = op.get_bind()

    # Check if we're using PostgreSQL
    if conn.dialect.name == "postgresql":
        # Check current column types before converting
        inspector = sa.inspect(conn)

        # Fix User table boolean columns
        users_columns = {col["name"]: col for col in inspector.get_columns("users")}

        if "is_active" in users_columns and str(
            users_columns["is_active"]["type"]
        ).upper() in ("INTEGER", "SMALLINT", "BIGINT"):
            # Convert is_active from INTEGER to BOOLEAN
            op.execute("ALTER TABLE users ALTER COLUMN is_active DROP DEFAULT")
            op.execute("""
                ALTER TABLE users 
                ALTER COLUMN is_active TYPE BOOLEAN 
                USING CASE WHEN is_active = 0 THEN FALSE ELSE TRUE END
            """)
            op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT true")

        if "is_verified" in users_columns and str(
            users_columns["is_verified"]["type"]
        ).upper() in ("INTEGER", "SMALLINT", "BIGINT"):
            # Convert is_verified from INTEGER to BOOLEAN
            op.execute("ALTER TABLE users ALTER COLUMN is_verified DROP DEFAULT")
            op.execute("""
                ALTER TABLE users 
                ALTER COLUMN is_verified TYPE BOOLEAN 
                USING CASE WHEN is_verified = 0 THEN FALSE ELSE TRUE END
            """)
            op.execute("ALTER TABLE users ALTER COLUMN is_verified SET DEFAULT false")

        # Fix ModelVersion table boolean column
        model_versions_columns = {
            col["name"]: col for col in inspector.get_columns("model_versions")
        }

        if "is_active" in model_versions_columns and str(
            model_versions_columns["is_active"]["type"]
        ).upper() in ("INTEGER", "SMALLINT", "BIGINT"):
            # Convert is_active from INTEGER to BOOLEAN
            op.execute("ALTER TABLE model_versions ALTER COLUMN is_active DROP DEFAULT")
            op.execute("""
                ALTER TABLE model_versions 
                ALTER COLUMN is_active TYPE BOOLEAN 
                USING CASE WHEN is_active = 0 THEN FALSE ELSE TRUE END
            """)
            op.execute(
                "ALTER TABLE model_versions ALTER COLUMN is_active SET DEFAULT false"
            )


def downgrade() -> None:
    """Convert User and ModelVersion boolean columns back to INTEGER."""
    conn = op.get_bind()

    if conn.dialect.name == "postgresql":
        # Revert User table
        op.execute("""
            ALTER TABLE users 
            ALTER COLUMN is_active TYPE INTEGER 
            USING CASE WHEN is_active THEN 1 ELSE 0 END
        """)
        op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT 1")

        op.execute("""
            ALTER TABLE users 
            ALTER COLUMN is_verified TYPE INTEGER 
            USING CASE WHEN is_verified THEN 1 ELSE 0 END
        """)
        op.execute("ALTER TABLE users ALTER COLUMN is_verified SET DEFAULT 0")

        # Revert ModelVersion table
        op.execute("""
            ALTER TABLE model_versions 
            ALTER COLUMN is_active TYPE INTEGER 
            USING CASE WHEN is_active THEN 1 ELSE 0 END
        """)
        op.execute("ALTER TABLE model_versions ALTER COLUMN is_active SET DEFAULT 0")
