"""add start/end columns to schedule_entries

Revision ID: 20260226_add_entry_start_end
Revises: 20260213_add_language_columns
Create Date: 2026-02-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260226_add_entry_start_end'
down_revision = '20260213_add_language_columns'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('schedule_entries'):
        cols = [c['name'] for c in inspector.get_columns('schedule_entries')]
        if 'start' not in cols:
            op.add_column('schedule_entries', sa.Column('start', sa.DateTime(timezone=True), nullable=True))
        if 'end' not in cols:
            op.add_column('schedule_entries', sa.Column('end', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('schedule_entries'):
        cols = [c['name'] for c in inspector.get_columns('schedule_entries')]
        if 'end' in cols:
            op.drop_column('schedule_entries', 'end')
        if 'start' in cols:
            op.drop_column('schedule_entries', 'start')
