"""add entry_history table for change tracking

Revision ID: 20260409_add_entry_history
Revises: 20260319_add_user_org_role_unique_idx
Create Date: 2026-04-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260409_add_entry_history'
down_revision = '20260319_add_user_org_role_unique_idx'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'entry_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('entry_id', sa.String(), nullable=True),
        sa.Column('schedule_id', sa.String(), nullable=False),
        sa.Column('changed_by_id', sa.String(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('snapshot', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['entry_id'], ['schedule_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_entry_history_entry_id', 'entry_history', ['entry_id'])
    op.create_index('ix_entry_history_schedule_id', 'entry_history', ['schedule_id'])


def downgrade():
    op.drop_index('ix_entry_history_schedule_id', table_name='entry_history')
    op.drop_index('ix_entry_history_entry_id', table_name='entry_history')
    op.drop_table('entry_history')
