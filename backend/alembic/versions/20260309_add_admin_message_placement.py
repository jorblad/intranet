"""add placement column to admin_messages

Revision ID: 20260309_add_admin_message_placement
Revises: 20260307_add_admin_message_translations
Create Date: 2026-03-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260309_add_admin_message_placement'
down_revision = '20260307_add_admin_message_translations'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('admin_messages'):
        cols = [c['name'] for c in inspector.get_columns('admin_messages')]
        if 'placement' not in cols:
            # add with server_default to backfill existing rows, keep non-nullable
            op.add_column('admin_messages', sa.Column('placement', sa.String(), nullable=False, server_default='banner'))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('admin_messages'):
        cols = [c['name'] for c in inspector.get_columns('admin_messages')]
        if 'placement' in cols:
            op.drop_column('admin_messages', 'placement')
