"""add language columns to users and organizations

Revision ID: 20260213_add_language_columns
Revises: add_org_fk_taxonomy
Create Date: 2026-02-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260213_add_language_columns'
down_revision = 'add_org_fk_taxonomy'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('users'):
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'language' not in user_cols:
            op.add_column('users', sa.Column('language', sa.String(), nullable=True))

    if inspector.has_table('organizations'):
        org_cols = [c['name'] for c in inspector.get_columns('organizations')]
        if 'language' not in org_cols:
            op.add_column('organizations', sa.Column('language', sa.String(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('organizations'):
        org_cols = [c['name'] for c in inspector.get_columns('organizations')]
        if 'language' in org_cols:
            op.drop_column('organizations', 'language')

    if inspector.has_table('users'):
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'language' in user_cols:
            op.drop_column('users', 'language')
