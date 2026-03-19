"""add unique index for user_organization_roles to prevent duplicate assignments

Revision ID: 20260319_add_user_org_role_unique_idx
Revises: 20260311_add_user_email
Create Date: 2026-03-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260319_add_user_org_role_unique_idx'
down_revision = '20260311_add_user_email'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Remove duplicate (user_id, role_id, organization_id) rows, keeping the
    # one with the smallest id per group. NULL organization_id is normalized to
    # empty string for grouping purposes, consistent with the unique index below.
    delete_sql = """
    WITH keep AS (
      SELECT min(id) AS keep_id,
             user_id,
             role_id,
             coalesce(organization_id, '') AS org_id
      FROM user_organization_roles
      GROUP BY user_id, role_id, coalesce(organization_id, '')
      HAVING count(*) > 1
    )
    DELETE FROM user_organization_roles
    WHERE id IN (
      SELECT r.id
      FROM user_organization_roles r
      JOIN keep k
        ON r.user_id = k.user_id
       AND r.role_id = k.role_id
       AND coalesce(r.organization_id, '') = k.org_id
       AND r.id <> k.keep_id
    );
    """
    try:
        conn.execute(sa.text(delete_sql))
    except Exception as exc:
        # Log the failure so operators can diagnose it; let subsequent index
        # creation fail (and be reported) if duplicates could not be removed.
        import logging
        logging.getLogger(__name__).warning(
            "user_organization_roles duplicate cleanup failed (will attempt index creation anyway): %s",
            exc,
        )

    # Create a uniqueness index to prevent future duplicate assignments.
    # NULL organization_id is normalized to '' so that two global (NULL-org)
    # assignments for the same (user_id, role_id) are treated as duplicates.
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_user_org_role_unique
            ON user_organization_roles (
                user_id,
                role_id,
                coalesce(organization_id, '')
            );
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS ux_user_org_role_unique;"
        )
    )
