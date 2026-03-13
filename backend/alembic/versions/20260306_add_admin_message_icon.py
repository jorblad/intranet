"""add icon column to admin_messages

Revision ID: 20260306_add_admin_message_icon
Revises: 20260305_add_user_personal_calendar_activities
Create Date: 2026-03-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260306_add_admin_message_icon'
down_revision = '20260305_add_user_personal_calendar_activities'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('admin_messages'):
        cols = [c['name'] for c in inspector.get_columns('admin_messages')]
        if 'icon' not in cols:
            op.add_column('admin_messages', sa.Column('icon', sa.String(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('admin_messages'):
        cols = [c['name'] for c in inspector.get_columns('admin_messages')]
        if 'icon' in cols:
            op.drop_column('admin_messages', 'icon')
