"""merge_staleness_and_repos

Revision ID: e734c8f0c44e
Revises: 20260419_merge_repos, l2m3n4o5p6q7
Create Date: 2026-04-27 02:54:51.667578

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e734c8f0c44e'
down_revision: Union[str, Sequence[str], None] = ('20260419_merge_repos', 'l2m3n4o5p6q7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
