"""add invitations and app_settings tables

Revision ID: 20260309_add_invitations_app_settings
Revises: 20260309_add_admin_message_placement
Create Date: 2026-03-09 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260309_add_invitations_app_settings'
down_revision = '20260309_add_admin_message_placement'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table('app_settings'):
        op.create_table(
            'app_settings',
            sa.Column('key', sa.String(), primary_key=True, nullable=False),
            sa.Column('value', sa.String(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )

    if not inspector.has_table('invitations'):
        op.create_table(
            'invitations',
            sa.Column('id', sa.String(), primary_key=True, nullable=False),
            sa.Column('token', sa.String(), nullable=False, unique=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('invitations'):
        op.drop_table('invitations')

    if inspector.has_table('app_settings'):
        op.drop_table('app_settings')
