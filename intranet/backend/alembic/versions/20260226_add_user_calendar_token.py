"""add calendar_token column to users

Revision ID: 20260226_add_user_calendar_token
Revises: 20260226_add_activity_default_times
Create Date: 2026-02-26 00:00:00.000002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260226_add_user_calendar_token'
down_revision = '20260226_add_activity_default_times'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('users'):
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'calendar_token' not in cols:
            op.add_column('users', sa.Column('calendar_token', sa.String(), nullable=True))
            # add unique index
            op.create_index('ix_users_calendar_token', 'users', ['calendar_token'], unique=True)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('users'):
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'calendar_token' in cols:
            try:
                op.drop_index('ix_users_calendar_token', table_name='users')
            except Exception:
                pass
            op.drop_column('users', 'calendar_token')
