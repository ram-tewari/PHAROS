"""phase2_drop_neo_alexandria_tables

Revision ID: ea5d03fc7e80
Revises: e734c8f0c44e
Create Date: 2026-07-18 14:42:44.590079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea5d03fc7e80'
down_revision: Union[str, Sequence[str], None] = 'e734c8f0c44e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables removed in the Phase 2 amputation (2026-07). Order matters on Postgres
# only when FKs exist between them; we use CASCADE there to be safe. The
# developer_profiles.user_id FK -> users.id is dropped by CASCADE when users goes.
_DROPPED_TABLES = [
    "collection_resources",
    "collections",
    "user_interactions",
    "user_profiles",
    "classification_codes",
    "authority_subjects",
    "authority_creators",
    "authority_publishers",
    "rag_evaluations",
    "ab_test_experiments",
    "prediction_logs",
    "retraining_runs",
    "model_versions",
    "users",
]


def upgrade() -> None:
    """Drop the Neo Alexandria tables. Idempotent (IF EXISTS) and dialect-aware."""
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    cascade = " CASCADE" if is_pg else ""
    for table in _DROPPED_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}"{cascade}')


def downgrade() -> None:
    """Irreversible. These tables belonged to the removed Neo Alexandria product;
    restoring them means restoring that code. Roll forward from a backup instead."""
    raise NotImplementedError(
        "Phase 2 table drops are not reversible; restore from a database backup."
    )
