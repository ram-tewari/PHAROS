"""Add authentication tables for Phase 17

Revision ID: 20260101_add_auth_tables
Revises: k1l2m3n4o5p6
Create Date: 2026-01-01 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PostgreSQL_UUID
from sqlalchemy.types import TypeDecorator, CHAR
import uuid


# revision identifiers, used by Alembic.
revision = "20260101_add_auth_tables"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


class GUID(TypeDecorator):
    """Platform-independent GUID type."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQL_UUID())
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return str(uuid.UUID(value))
            else:
                return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            else:
                return value


def upgrade() -> None:
    """Add tier column to users table and create oauth_accounts table."""

    # Add tier column to existing users table
    op.add_column(
        "users", sa.Column("tier", sa.String(20), nullable=False, server_default="free")
    )

    # Create oauth_accounts table
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for oauth_accounts table
    op.create_index(
        op.f("ix_oauth_accounts_id"), "oauth_accounts", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_oauth_accounts_provider_user"),
        "oauth_accounts",
        ["provider", "provider_user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop oauth_accounts table and tier column."""

    # Drop oauth_accounts table
    op.drop_index(op.f("ix_oauth_accounts_provider_user"), table_name="oauth_accounts")
    op.drop_index(op.f("ix_oauth_accounts_id"), table_name="oauth_accounts")
    op.drop_table("oauth_accounts")

    # Drop tier column from users table
    op.drop_column("users", "tier")
