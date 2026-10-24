"""merge_heads

Revision ID: b4b05068fe27
Revises: 20260108_add_authority_timestamps, 20260116_add_version_column
Create Date: 2026-01-23 16:19:53.661202

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4b05068fe27"
down_revision: Union[str, Sequence[str], None] = (
    "20260108_add_authority_timestamps",
    "20260116_add_version_column",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
