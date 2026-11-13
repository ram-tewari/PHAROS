"""Memory items that prove themselves (Phase 3, stage S2).

Adds to ``memory_items``: ``predicate`` (a checkable rule in JSON form),
``holdout`` (the backtest that decided the item's status), ``strength``
(requirement | observation | advisory) and the utility counters ``served``,
``complied`` and ``helped`` that a later stage fills. Purely additive.

Revision ID: 0005_memory_checks
Revises: 0004_learning
Create Date: 2026-11-13 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005_memory_checks'
down_revision: str | Sequence[str] | None = '0004_learning'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COUNTERS = ('served', 'complied', 'helped')


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('memory_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('predicate', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('holdout', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('strength', sa.String(length=16), nullable=True))
        for name in _COUNTERS:
            batch_op.add_column(sa.Column(name, sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('memory_items', schema=None) as batch_op:
        for name in reversed(_COUNTERS):
            batch_op.drop_column(name)
        batch_op.drop_column('strength')
        batch_op.drop_column('holdout')
        batch_op.drop_column('predicate')
