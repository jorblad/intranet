"""add unique index for schedules to avoid duplicates

Revision ID: 20260302_schedule_unique_idx
Revises: 20260226_add_entry_start_end
Create Date: 2026-03-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260302_schedule_unique_idx'
down_revision = '20260226_add_entry_start_end'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Remove simple duplicate rows keeping the one with smallest id
    # Normalize NULL organization_id by coalescing to empty string for grouping
    delete_sql = """
    WITH keep AS (
      SELECT min(id) AS keep_id, name, term_id, coalesce(CAST(activity_id AS text), '') AS activity_id, coalesce(CAST(organization_id AS text), '') AS organization_id
      FROM schedules
      GROUP BY name, term_id, coalesce(CAST(activity_id AS text), ''), coalesce(CAST(organization_id AS text), '')
      HAVING count(*) > 1
    )
    DELETE FROM schedules s
    USING keep k
    WHERE coalesce(CAST(s.activity_id AS text), '') = k.activity_id
      AND coalesce(CAST(s.organization_id AS text), '') = k.organization_id
      AND s.name = k.name
      AND s.term_id = k.term_id
      AND s.id <> k.keep_id;
    """
    try:
        conn.execute(sa.text(delete_sql))
    except Exception:
        # If deletion fails, let index creation fail so operator can manually inspect DB
        pass

    # Create a uniqueness index to prevent future duplicates.
    # Use expression columns so that NULL organization_id (and activity_id) are
    # normalized consistently with the cleanup above and treated as duplicates.
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX ux_schedules_name_term_activity_org
            ON schedules (
                name,
                term_id,
                coalesce(CAST(activity_id AS text), ''),
                coalesce(CAST(organization_id AS text), '')
            );
            """
        )
    )


def downgrade():
    # Drop the expression unique index created in upgrade()
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS ux_schedules_name_term_activity_org;"
        )
    )
