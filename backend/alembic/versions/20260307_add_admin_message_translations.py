"""add title_i18n and body_i18n columns to admin_messages

Revision ID: 20260307_add_admin_message_translations
Revises: 20260306_add_admin_message_icon
Create Date: 2026-03-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260307_add_admin_message_translations'
down_revision = '20260306_add_admin_message_icon'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('admin_messages'):
        cols = [c['name'] for c in inspector.get_columns('admin_messages')]
        if 'title_i18n' not in cols:
            op.add_column('admin_messages', sa.Column('title_i18n', sa.JSON(), nullable=True))
        if 'body_i18n' not in cols:
            op.add_column('admin_messages', sa.Column('body_i18n', sa.JSON(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('admin_messages'):
        cols = [c['name'] for c in inspector.get_columns('admin_messages')]
        if 'title_i18n' in cols:
            op.drop_column('admin_messages', 'title_i18n')
        if 'body_i18n' in cols:
            op.drop_column('admin_messages', 'body_i18n')
