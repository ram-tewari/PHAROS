"""Add coding_profiles table and profile_id FK on proposed_rules

Revision ID: 20260410_coding_profiles
Revises: 20260410_pgvector_splade
Create Date: 2026-04-10

Implements the Master Programmer Personalities feature:
1. Creates coding_profiles table for reusable coding personalities
2. Adds profile_id nullable FK on proposed_rules (NULL = personal baseline)
3. Adds composite index on (profile_id, status) for context assembly queries
"""
from alembic import op
import sqlalchemy as sa


revision = '20260410_coding_profiles'
down_revision = '20260410_pgvector_splade'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the coding_profiles table
    op.create_table(
        'coding_profiles',
        sa.Column('id', sa.String(128), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('best_suited_for', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index('ix_coding_profiles_name', 'coding_profiles', ['name'])

    # 2. Add profile_id FK column to proposed_rules
    # For SQLite, we need to use batch mode to add FK constraints
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    if dialect_name == 'sqlite':
        # SQLite: Use batch mode for FK constraint
        with op.batch_alter_table('proposed_rules', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'profile_id',
                    sa.String(128),
                    nullable=True,
                )
            )
            batch_op.create_foreign_key(
                'fk_proposed_rules_profile_id',
                'coding_profiles',
                ['profile_id'],
                ['id'],
                ondelete='SET NULL'
            )
            batch_op.create_index(
                'ix_proposed_rules_profile_id',
                ['profile_id']
            )
            batch_op.create_index(
                'ix_proposed_rules_profile_status',
                ['profile_id', 'status']
            )
    else:
        # PostgreSQL: Direct column addition with FK
        op.add_column(
            'proposed_rules',
            sa.Column(
                'profile_id',
                sa.String(128),
                sa.ForeignKey('coding_profiles.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )
        op.create_index(
            'ix_proposed_rules_profile_id', 'proposed_rules', ['profile_id']
        )
        op.create_index(
            'ix_proposed_rules_profile_status',
            'proposed_rules',
            ['profile_id', 'status'],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    if dialect_name == 'sqlite':
        # SQLite: Use batch mode
        with op.batch_alter_table('proposed_rules', schema=None) as batch_op:
            batch_op.drop_index('ix_proposed_rules_profile_status')
            batch_op.drop_index('ix_proposed_rules_profile_id')
            batch_op.drop_constraint('fk_proposed_rules_profile_id', type_='foreignkey')
            batch_op.drop_column('profile_id')
    else:
        # PostgreSQL: Direct operations
        op.drop_index('ix_proposed_rules_profile_status', table_name='proposed_rules')
        op.drop_index('ix_proposed_rules_profile_id', table_name='proposed_rules')
        op.drop_column('proposed_rules', 'profile_id')
    
    op.drop_index('ix_coding_profiles_name', table_name='coding_profiles')
    op.drop_table('coding_profiles')
