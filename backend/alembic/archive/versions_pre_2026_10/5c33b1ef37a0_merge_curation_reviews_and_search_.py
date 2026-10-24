"""merge curation_reviews and search_vector branches

Revision ID: 5c33b1ef37a0
Revises: z1y2x3w4v5u6, k1l2m3n4o5p6
Create Date: 2025-12-31 06:28:13.597261

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "5c33b1ef37a0"
down_revision: Union[str, Sequence[str], None] = ("z1y2x3w4v5u6", "k1l2m3n4o5p6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
