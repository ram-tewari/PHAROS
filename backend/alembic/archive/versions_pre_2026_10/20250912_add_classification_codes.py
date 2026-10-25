"""add classification_codes table and seed data

Revision ID: 20250912_add_classification_codes
Revises: 20250911_add_ingestion_status_fields
Create Date: 2025-09-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20250912_add_classification_codes"
down_revision = "20250911_add_ingestion_status_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classification_codes",
        sa.Column("code", sa.String(length=3), primary_key=True, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "parent_code",
            sa.String(length=3),
            sa.ForeignKey("classification_codes.code"),
            nullable=True,
        ),
        sa.Column(
            "keywords",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
            server_default="[]",
        ),
    )

    # Seed top-level UDC-inspired codes
    seeds = [
        (
            "000",
            "Computer Science, Information & General Works",
            "General knowledge, computing, information science",
            None,
            [
                "programming",
                "software",
                "coding",
                "developer",
                "python",
                "java",
                "javascript",
                "typescript",
                "c++",
                "c#",
                "go",
                "rust",
                "algorithm",
                "data structure",
                "computer",
                "computing",
                "information",
            ],
        ),
        ("100", "Philosophy & Psychology", None, None, []),
        ("200", "Religion & Theology", None, None, []),
        ("300", "Social Sciences", None, None, []),
        (
            "400",
            "Language & Linguistics",
            "Languages, linguistics, grammar and related topics",
            None,
            [
                "language",
                "linguistics",
                "grammar",
                "vocabulary",
                "pronunciation",
                "syntax",
                "semantics",
                "phonetics",
                "morphology",
            ],
        ),
        (
            "500",
            "Pure Sciences",
            "Mathematics, physics, chemistry, biology, etc.",
            None,
            [
                "science",
                "physics",
                "chemistry",
                "biology",
                "mathematics",
                "math",
                "algebra",
                "calculus",
                "astronomy",
                "geology",
                "ecology",
                "zoology",
                "botany",
            ],
        ),
        ("600", "Technology & Applied Sciences", None, None, []),
        ("700", "Arts & Recreation", None, None, []),
        ("800", "Literature", None, None, []),
        (
            "900",
            "History & Geography",
            "Historical events, figures, and geography",
            None,
            [
                "history",
                "ancient",
                "medieval",
                "renaissance",
                "empire",
                "revolution",
                "napoleon",
                "rome",
                "greece",
                "wwi",
                "wwii",
                "cold war",
                "geography",
            ],
        ),
    ]

    for code, title, description, parent_code, keywords in seeds:
        # Use bind parameters properly with sa.text()
        bind = op.get_bind()
        stmt = sa.text(
            "INSERT INTO classification_codes (code, title, description, parent_code, keywords) "
            "VALUES (:code, :title, :description, :parent_code, CAST(:keywords AS JSON))"
        )
        bind.execute(
            stmt,
            {
                "code": code,
                "title": title,
                "description": description,
                "parent_code": parent_code,
                "keywords": str(keywords).replace(
                    "'", '"'
                ),  # Convert Python list to JSON string
            },
        )
        # Fallback for SQLite which supports JSON natively via Python binding
        if op.get_bind().dialect.name != "postgresql":
            import json

            op.execute(
                sa.text(
                    "UPDATE classification_codes SET keywords=:kw WHERE code=:code"
                ).bindparams(kw=json.dumps(keywords), code=code)
            )


def downgrade() -> None:
    op.drop_table("classification_codes")
