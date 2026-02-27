"""add default start/end time columns to activities

Revision ID: 20260226_add_activity_default_times
Revises: 20260226_add_entry_start_end
Create Date: 2026-02-26 00:00:00.000001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260226_add_activity_default_times'
down_revision = '20260226_add_entry_start_end'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('activities'):
        cols = [c['name'] for c in inspector.get_columns('activities')]
        if 'default_start_time' not in cols:
            op.add_column('activities', sa.Column('default_start_time', sa.Time(), nullable=True))
        if 'default_end_time' not in cols:
            op.add_column('activities', sa.Column('default_end_time', sa.Time(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('activities'):
        cols = [c['name'] for c in inspector.get_columns('activities')]
        if 'default_end_time' in cols:
            op.drop_column('activities', 'default_end_time')
        if 'default_start_time' in cols:
            op.drop_column('activities', 'default_start_time')
