"""merge_all_heads

Revision ID: 25c9c391cb35
Revises: 20260410_coding_profiles, 20260410_github_remote_ptrs, a7f8e9d0c1b2, 39167d546c0c
Create Date: 2026-04-11 19:06:09.527425

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25c9c391cb35'
down_revision: Union[str, Sequence[str], None] = ('20260410_coding_profiles', '20260410_github_remote_ptrs', 'a7f8e9d0c1b2', '39167d546c0c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
