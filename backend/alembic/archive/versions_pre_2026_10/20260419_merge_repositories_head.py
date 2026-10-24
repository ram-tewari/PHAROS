"""merge repositories head with metadata branch

Revision ID: 20260419_merge_repos
Revises: 20260419_repositories, cf3db55407e5
Create Date: 2026-04-19 08:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260419_merge_repos'
down_revision = ('20260419_repositories', 'cf3db55407e5')
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration - no schema changes needed
    pass


def downgrade():
    pass
