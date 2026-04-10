"""Update users table schema with missing auth fields

Revision ID: 20260105_update_users_table
Revises: 20260105_add_metadata
Create Date: 2026-01-05 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260105_update_users_table"
down_revision = "20260105_add_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing columns to users table for authentication."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    # Add hashed_password column if it doesn't exist
    if "hashed_password" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "hashed_password", sa.String(255), nullable=False, server_default=""
            ),
        )

    # Add full_name column if it doesn't exist
    if "full_name" not in existing_columns:
        op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))

    # Add bio column if it doesn't exist
    if "bio" not in existing_columns:
        op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))

    # Add avatar_url column if it doesn't exist
    if "avatar_url" not in existing_columns:
        op.add_column("users", sa.Column("avatar_url", sa.String(512), nullable=True))

    # Add role column if it doesn't exist
    if "role" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        )

    # Add is_active column if it doesn't exist
    if "is_active" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        )

    # Add is_verified column if it doesn't exist
    if "is_verified" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("is_verified", sa.Integer(), nullable=False, server_default="0"),
        )

    # Add last_login column if it doesn't exist
    if "last_login" not in existing_columns:
        op.add_column(
            "users", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True)
        )

    # Add updated_at column if it doesn't exist
    if "updated_at" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

    # Create unique constraints on email and username if they don't exist
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("users")}

    if "ix_users_email" not in existing_indexes:
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    if "ix_users_username" not in existing_indexes:
        op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)


def downgrade() -> None:
    """Remove added columns from users table."""

    # Drop indexes
    try:
        op.drop_index(op.f("ix_users_username"), table_name="users")
    except:
        pass

    try:
        op.drop_index(op.f("ix_users_email"), table_name="users")
    except:
        pass

    # Drop columns
    op.drop_column("users", "updated_at")
    op.drop_column("users", "last_login")
    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "bio")
    op.drop_column("users", "full_name")
    op.drop_column("users", "hashed_password")
