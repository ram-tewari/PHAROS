"""Add SQLite FTS5 contentless index and sync triggers for resources

Revision ID: a3c1f7e2b9d0
Revises: f3e272b2b6cd
Create Date: 2025-09-10 12:00:00.000000

Notes:
- This migration is a no-op on non-SQLite engines.
- It guards execution if FTS5 is not available in the SQLite build.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.engine import Connection


# revision identifiers, used by Alembic.
revision: str = "20250910_add_fts_and_triggers"
down_revision: Union[str, Sequence[str], None] = "f3e272b2b6cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sqlite_has_fts5(conn: Connection) -> bool:
    try:
        rows = conn.exec_driver_sql("PRAGMA compile_options;").fetchall()
        options = {row[0] for row in rows}
        if any("FTS5" in opt for opt in options):
            return True
    except Exception:
        pass
    # Fallback probe: attempt to create and drop a temp fts5 table
    try:
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE IF NOT EXISTS temp.__fts5_probe USING fts5(x);"
        )
        conn.exec_driver_sql("DROP TABLE IF EXISTS temp.__fts5_probe;")
        return True
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        # Non-SQLite: no-op to keep portability
        return

    if not _sqlite_has_fts5(conn):
        # FTS5 not available: no-op with clear comment.
        # Users can still use fallback keyword search.
        return

    # Mapping table for UUID <-> rowid
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS resources_fts_doc (
            rowid INTEGER PRIMARY KEY,
            resource_id TEXT UNIQUE NOT NULL
        );
        """
    )

    # Contentless FTS5 table (title, description)
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
            title,
            description,
            content=''
        );
        """
    )

    # AFTER INSERT trigger: ensure mapping row and insert into FTS
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_resources_ai_fts
        AFTER INSERT ON resources
        BEGIN
            INSERT OR IGNORE INTO resources_fts_doc(resource_id) VALUES (NEW.id);
            INSERT INTO resources_fts(rowid, title, description)
            VALUES (
                (SELECT rowid FROM resources_fts_doc WHERE resource_id = NEW.id),
                NEW.title,
                COALESCE(NEW.description, '')
            );
        END;
        """
    )

    # AFTER UPDATE trigger on title, description: update FTS row
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_resources_au_fts
        AFTER UPDATE OF title, description ON resources
        BEGIN
            UPDATE resources_fts
            SET title = NEW.title,
                description = COALESCE(NEW.description, '')
            WHERE rowid = (
                SELECT rowid FROM resources_fts_doc WHERE resource_id = NEW.id
            );
        END;
        """
    )

    # AFTER DELETE trigger: remove FTS row and mapping row
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_resources_ad_fts
        AFTER DELETE ON resources
        BEGIN
            DELETE FROM resources_fts
            WHERE rowid = (
                SELECT rowid FROM resources_fts_doc WHERE resource_id = OLD.id
            );
            DELETE FROM resources_fts_doc WHERE resource_id = OLD.id;
        END;
        """
    )

    # Pre-populate mapping and FTS rows for existing data
    # 1) Ensure mapping rows exist for all resources
    op.execute(
        """
        INSERT OR IGNORE INTO resources_fts_doc(resource_id)
        SELECT id FROM resources;
        """
    )

    # 2) Insert missing FTS rows for those mappings
    op.execute(
        """
        INSERT INTO resources_fts(rowid, title, description)
        SELECT d.rowid, r.title, COALESCE(r.description, '')
        FROM resources r
        JOIN resources_fts_doc d ON d.resource_id = r.id
        WHERE d.rowid NOT IN (SELECT rowid FROM resources_fts);
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return

    # Drop triggers first (idempotent)
    op.execute("DROP TRIGGER IF EXISTS trg_resources_ad_fts;")
    op.execute("DROP TRIGGER IF EXISTS trg_resources_au_fts;")
    op.execute("DROP TRIGGER IF EXISTS trg_resources_ai_fts;")

    # Drop FTS and mapping tables
    op.execute("DROP TABLE IF EXISTS resources_fts;")
    op.execute("DROP TABLE IF EXISTS resources_fts_doc;")
