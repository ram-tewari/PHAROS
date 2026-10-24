"""Add Advanced RAG Tables

Revision ID: 20260103_add_advanced_rag_tables
Revises: cc6095f314dd
Create Date: 2026-01-03 02:50:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260103_add_advanced_rag_tables"
down_revision: Union[str, Sequence[str], None] = "cc6095f314dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Advanced RAG tables for Phase 17.5."""
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    import uuid

    # Determine UUID type based on dialect
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        uuid_type = PG_UUID(as_uuid=True)
    else:
        uuid_type = sa.CHAR(36)

    # Create document_chunks table
    op.create_table(
        "document_chunks",
        sa.Column("id", uuid_type, nullable=False, default=uuid.uuid4),
        sa.Column("resource_id", uuid_type, nullable=False),
        sa.Column("embedding_id", uuid_type, nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chunk_resource", "document_chunks", ["resource_id"])
    op.create_index(
        "idx_chunk_resource_index", "document_chunks", ["resource_id", "chunk_index"]
    )

    # Create graph_entities table
    op.create_table(
        "graph_entities",
        sa.Column("id", uuid_type, nullable=False, default=uuid.uuid4),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_entity_name_type", "graph_entities", ["name", "type"])

    # Create graph_relationships table
    op.create_table(
        "graph_relationships",
        sa.Column("id", uuid_type, nullable=False, default=uuid.uuid4),
        sa.Column("source_entity_id", uuid_type, nullable=False),
        sa.Column("target_entity_id", uuid_type, nullable=False),
        sa.Column("provenance_chunk_id", uuid_type, nullable=True),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_entity_id"], ["graph_entities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"], ["graph_entities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["provenance_chunk_id"], ["document_chunks.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_relationship_source", "graph_relationships", ["source_entity_id"]
    )
    op.create_index(
        "idx_relationship_target", "graph_relationships", ["target_entity_id"]
    )
    op.create_index("idx_relationship_type", "graph_relationships", ["relation_type"])

    # Create synthetic_questions table
    op.create_table(
        "synthetic_questions",
        sa.Column("id", uuid_type, nullable=False, default=uuid.uuid4),
        sa.Column("chunk_id", uuid_type, nullable=False),
        sa.Column("embedding_id", uuid_type, nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_synthetic_chunk", "synthetic_questions", ["chunk_id"])

    # Create rag_evaluations table
    op.create_table(
        "rag_evaluations",
        sa.Column("id", uuid_type, nullable=False, default=uuid.uuid4),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column("generated_answer", sa.Text(), nullable=True),
        sa.Column(
            "retrieved_chunk_ids", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("answer_relevance_score", sa.Float(), nullable=True),
        sa.Column("context_precision_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_evaluation_created", "rag_evaluations", ["created_at"])


def downgrade() -> None:
    """Remove Advanced RAG tables."""

    # Drop tables in reverse order (respecting foreign keys)
    op.drop_index("idx_evaluation_created", table_name="rag_evaluations")
    op.drop_table("rag_evaluations")

    op.drop_index("idx_synthetic_chunk", table_name="synthetic_questions")
    op.drop_table("synthetic_questions")

    op.drop_index("idx_relationship_type", table_name="graph_relationships")
    op.drop_index("idx_relationship_target", table_name="graph_relationships")
    op.drop_index("idx_relationship_source", table_name="graph_relationships")
    op.drop_table("graph_relationships")

    op.drop_index("idx_entity_name_type", table_name="graph_entities")
    op.drop_table("graph_entities")

    op.drop_index("idx_chunk_resource_index", table_name="document_chunks")
    op.drop_index("idx_chunk_resource", table_name="document_chunks")
    op.drop_table("document_chunks")
