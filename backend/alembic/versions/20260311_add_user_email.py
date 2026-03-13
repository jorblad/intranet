"""add email column to users

Revision ID: 20260311_add_user_email
Revises: 20260309_add_invitations_app_settings
Create Date: 2026-03-11 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260311_add_user_email'
down_revision = '20260309_add_invitations_app_settings'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('users'):
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'email' not in user_cols:
            op.add_column('users', sa.Column('email', sa.String(), nullable=True))
        # create a unique index for email if missing to match the model constraint
        existing_idx = [i['name'] for i in inspector.get_indexes('users')]
        if 'ix_users_email' not in existing_idx:
            op.create_index('ix_users_email', 'users', ['email'], unique=True)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('users'):
        existing_idx = [i['name'] for i in inspector.get_indexes('users')]
        if 'ix_users_email' in existing_idx:
            op.drop_index('ix_users_email', table_name='users')
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'email' in user_cols:
            op.drop_column('users', 'email')
