"""merge_heads

Revision ID: 08fc64e7d3b0
Revises: 20260123_centrality, 4b863b20cf62
Create Date: 2026-01-23 17:02:21.029459

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "08fc64e7d3b0"
down_revision: Union[str, Sequence[str], None] = ("20260123_centrality", "4b863b20cf62")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
