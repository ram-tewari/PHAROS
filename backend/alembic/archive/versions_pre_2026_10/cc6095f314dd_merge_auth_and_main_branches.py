"""Merge auth and main branches

Revision ID: cc6095f314dd
Revises: 20260101_add_auth_tables, 5c33b1ef37a0
Create Date: 2026-01-03 02:42:11.421651

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "cc6095f314dd"
down_revision: Union[str, Sequence[str], None] = (
    "20260101_add_auth_tables",
    "5c33b1ef37a0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
