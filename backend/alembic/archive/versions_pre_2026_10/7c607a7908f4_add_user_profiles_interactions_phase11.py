"""add_user_profiles_interactions_phase11

Revision ID: 7c607a7908f4
Revises: a1b2c3d4e5f6, h8i9j0k1l2m3
Create Date: 2025-11-15 14:06:42.403070

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7c607a7908f4"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f6", "h8i9j0k1l2m3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
        return index_name in indexes
    except Exception:
        return False


def upgrade() -> None:
    """
    Upgrade schema - Add Phase 11 recommendation engine tables.

    Creates:
    - users: Basic user entity for authentication
    - user_profiles: User preferences and learned patterns
    - user_interactions: Interaction tracking with implicit feedback
    - recommendation_feedback: Recommendation performance tracking
    """

    # Get database connection for dialect-specific operations
    conn = op.get_bind()

    # Define GUID type based on dialect
    if conn.dialect.name == "postgresql":
        guid_type = postgresql.UUID()
    else:
        guid_type = sa.CHAR(36)

    # Create users table if it doesn't exist
    if not table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", guid_type, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("username", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
            sa.UniqueConstraint("username"),
        )
        print("Created users table")
    else:
        print("users table already exists")

    # Create indexes for users table
    if not index_exists("users", "ix_users_email"):
        op.create_index("ix_users_email", "users", ["email"])
    if not index_exists("users", "ix_users_username"):
        op.create_index("ix_users_username", "users", ["username"])

    # Create user_profiles table if it doesn't exist
    if not table_exists("user_profiles"):
        op.create_table(
            "user_profiles",
            sa.Column("id", guid_type, nullable=False),
            sa.Column("user_id", guid_type, nullable=False),
            sa.Column("research_domains", sa.Text(), nullable=True),
            sa.Column("active_domain", sa.String(length=255), nullable=True),
            sa.Column("preferred_taxonomy_ids", sa.Text(), nullable=True),
            sa.Column("preferred_authors", sa.Text(), nullable=True),
            sa.Column("preferred_sources", sa.Text(), nullable=True),
            sa.Column("excluded_sources", sa.Text(), nullable=True),
            sa.Column(
                "diversity_preference", sa.Float(), server_default="0.5", nullable=False
            ),
            sa.Column(
                "novelty_preference", sa.Float(), server_default="0.3", nullable=False
            ),
            sa.Column("recency_bias", sa.Float(), server_default="0.5", nullable=False),
            sa.Column(
                "total_interactions", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column("avg_session_duration", sa.Float(), nullable=True),
            sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        print("Created user_profiles table")
    else:
        print("user_profiles table already exists")

    # Create index for user_profiles
    if not index_exists("user_profiles", "idx_user_profiles_user"):
        op.create_index(
            "idx_user_profiles_user", "user_profiles", ["user_id"], unique=True
        )

    # Add check constraints for preference ranges (0.0-1.0)
    if conn.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_user_profiles_diversity_range",
            "user_profiles",
            "diversity_preference >= 0.0 AND diversity_preference <= 1.0",
        )
        op.create_check_constraint(
            "ck_user_profiles_novelty_range",
            "user_profiles",
            "novelty_preference >= 0.0 AND novelty_preference <= 1.0",
        )
        op.create_check_constraint(
            "ck_user_profiles_recency_range",
            "user_profiles",
            "recency_bias >= 0.0 AND recency_bias <= 1.0",
        )

    # Create user_interactions table if it doesn't exist
    if not table_exists("user_interactions"):
        op.create_table(
            "user_interactions",
            sa.Column("id", guid_type, nullable=False),
            sa.Column("user_id", guid_type, nullable=False),
            sa.Column("resource_id", guid_type, nullable=False),
            sa.Column("interaction_type", sa.String(length=50), nullable=False),
            sa.Column(
                "interaction_strength", sa.Float(), server_default="0.0", nullable=False
            ),
            sa.Column("dwell_time", sa.Integer(), nullable=True),
            sa.Column("scroll_depth", sa.Float(), nullable=True),
            sa.Column(
                "annotation_count", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column(
                "return_visits", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column("rating", sa.Integer(), nullable=True),
            sa.Column("session_id", sa.String(length=255), nullable=True),
            sa.Column(
                "interaction_timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("is_positive", sa.Integer(), server_default="0", nullable=False),
            sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["resource_id"], ["resources.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        print("Created user_interactions table")
    else:
        print("user_interactions table already exists")

    # Create indexes for user_interactions
    if not index_exists("user_interactions", "ix_user_interactions_user_id"):
        op.create_index(
            "ix_user_interactions_user_id", "user_interactions", ["user_id"]
        )
    if not index_exists("user_interactions", "ix_user_interactions_resource_id"):
        op.create_index(
            "ix_user_interactions_resource_id", "user_interactions", ["resource_id"]
        )
    if not index_exists("user_interactions", "idx_user_interactions_user_resource"):
        op.create_index(
            "idx_user_interactions_user_resource",
            "user_interactions",
            ["user_id", "resource_id"],
        )
    if not index_exists("user_interactions", "idx_user_interactions_timestamp"):
        op.create_index(
            "idx_user_interactions_timestamp",
            "user_interactions",
            ["interaction_timestamp"],
        )

    # Create recommendation_feedback table if it doesn't exist
    if not table_exists("recommendation_feedback"):
        op.create_table(
            "recommendation_feedback",
            sa.Column("id", guid_type, nullable=False),
            sa.Column("user_id", guid_type, nullable=False),
            sa.Column("resource_id", guid_type, nullable=False),
            sa.Column("recommendation_strategy", sa.String(length=50), nullable=False),
            sa.Column("recommendation_score", sa.Float(), nullable=False),
            sa.Column("rank_position", sa.Integer(), nullable=False),
            sa.Column("was_clicked", sa.Integer(), server_default="0", nullable=False),
            sa.Column("was_useful", sa.Integer(), nullable=True),
            sa.Column("feedback_notes", sa.Text(), nullable=True),
            sa.Column(
                "recommended_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["resource_id"], ["resources.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        print("Created recommendation_feedback table")
    else:
        print("recommendation_feedback table already exists")

    # Create indexes for recommendation_feedback
    if not index_exists("recommendation_feedback", "idx_recommendation_feedback_user"):
        op.create_index(
            "idx_recommendation_feedback_user", "recommendation_feedback", ["user_id"]
        )
    if not index_exists(
        "recommendation_feedback", "idx_recommendation_feedback_resource"
    ):
        op.create_index(
            "idx_recommendation_feedback_resource",
            "recommendation_feedback",
            ["resource_id"],
        )
    if not index_exists(
        "recommendation_feedback", "idx_recommendation_feedback_strategy"
    ):
        op.create_index(
            "idx_recommendation_feedback_strategy",
            "recommendation_feedback",
            ["recommendation_strategy"],
        )


def downgrade() -> None:
    """
    Downgrade schema - Remove Phase 11 recommendation engine tables.

    Drops tables in reverse order to respect foreign key constraints.
    """

    # Get database connection for dialect-specific operations
    conn = op.get_bind()

    # Drop recommendation_feedback table and its indexes
    if table_exists("recommendation_feedback"):
        if index_exists(
            "recommendation_feedback", "idx_recommendation_feedback_strategy"
        ):
            op.drop_index(
                "idx_recommendation_feedback_strategy",
                table_name="recommendation_feedback",
            )
        if index_exists(
            "recommendation_feedback", "idx_recommendation_feedback_resource"
        ):
            op.drop_index(
                "idx_recommendation_feedback_resource",
                table_name="recommendation_feedback",
            )
        if index_exists("recommendation_feedback", "idx_recommendation_feedback_user"):
            op.drop_index(
                "idx_recommendation_feedback_user", table_name="recommendation_feedback"
            )
        op.drop_table("recommendation_feedback")
        print("Dropped recommendation_feedback table")

    # Drop user_interactions table and its indexes
    if table_exists("user_interactions"):
        if index_exists("user_interactions", "idx_user_interactions_timestamp"):
            op.drop_index(
                "idx_user_interactions_timestamp", table_name="user_interactions"
            )
        if index_exists("user_interactions", "idx_user_interactions_user_resource"):
            op.drop_index(
                "idx_user_interactions_user_resource", table_name="user_interactions"
            )
        if index_exists("user_interactions", "ix_user_interactions_resource_id"):
            op.drop_index(
                "ix_user_interactions_resource_id", table_name="user_interactions"
            )
        if index_exists("user_interactions", "ix_user_interactions_user_id"):
            op.drop_index(
                "ix_user_interactions_user_id", table_name="user_interactions"
            )
        op.drop_table("user_interactions")
        print("Dropped user_interactions table")

    # Drop user_profiles table, its indexes, and check constraints
    if table_exists("user_profiles"):
        if conn.dialect.name == "postgresql":
            op.drop_constraint(
                "ck_user_profiles_recency_range", "user_profiles", type_="check"
            )
            op.drop_constraint(
                "ck_user_profiles_novelty_range", "user_profiles", type_="check"
            )
            op.drop_constraint(
                "ck_user_profiles_diversity_range", "user_profiles", type_="check"
            )

        if index_exists("user_profiles", "idx_user_profiles_user"):
            op.drop_index("idx_user_profiles_user", table_name="user_profiles")
        op.drop_table("user_profiles")
        print("Dropped user_profiles table")

    # Drop users table and its indexes
    if table_exists("users"):
        if index_exists("users", "ix_users_username"):
            op.drop_index("ix_users_username", table_name="users")
        if index_exists("users", "ix_users_email"):
            op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
        print("Dropped users table")
