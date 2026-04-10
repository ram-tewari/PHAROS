"""add authority timestamps

Revision ID: 20260108_add_authority_timestamps
Revises: 20260108_fix_user_boolean_columns
Create Date: 2026-01-08 06:58:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260108_add_authority_timestamps"
down_revision = "20260108_fix_user_boolean_columns"
branch_labels = None
depends_on = None


def upgrade():
    # Add created_at and updated_at to authority_subjects if they don't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='authority_subjects' AND column_name='created_at') THEN
                ALTER TABLE authority_subjects ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='authority_subjects' AND column_name='updated_at') THEN
                ALTER TABLE authority_subjects ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
        END $$;
    """)

    # Add created_at and updated_at to authority_creators if they don't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='authority_creators' AND column_name='created_at') THEN
                ALTER TABLE authority_creators ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='authority_creators' AND column_name='updated_at') THEN
                ALTER TABLE authority_creators ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
        END $$;
    """)

    # Add created_at and updated_at to authority_publishers if they don't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='authority_publishers' AND column_name='created_at') THEN
                ALTER TABLE authority_publishers ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='authority_publishers' AND column_name='updated_at') THEN
                ALTER TABLE authority_publishers ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
        END $$;
    """)


def downgrade():
    # Remove the columns if needed
    op.execute("ALTER TABLE authority_subjects DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE authority_subjects DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE authority_creators DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE authority_creators DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE authority_publishers DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE authority_publishers DROP COLUMN IF EXISTS updated_at")
