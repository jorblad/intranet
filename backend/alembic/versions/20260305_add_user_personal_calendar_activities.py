"""add personal_calendar_activity_ids column to users

Revision ID: 20260305_add_user_personal_calendar_activities
Revises: 20260302_schedule_unique_idx
Create Date: 2026-03-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260305_add_user_personal_calendar_activities'
down_revision = '20260302_schedule_unique_idx'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('users'):
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'personal_calendar_activity_ids' not in cols:
            op.add_column('users', sa.Column('personal_calendar_activity_ids', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('users'):
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'personal_calendar_activity_ids' in cols:
            op.drop_column('users', 'personal_calendar_activity_ids')
