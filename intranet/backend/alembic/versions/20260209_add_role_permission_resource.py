"""add role_permission_resources table

Revision ID: 20260209_add_role_permission_resource
Revises: 
Create Date: 2026-02-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260209_rpr'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'role_permission_resources',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('role_id', sa.String(), sa.ForeignKey('roles.id'), nullable=False),
        sa.Column('permission_id', sa.String(), sa.ForeignKey('permissions.id'), nullable=False),
        sa.Column('resource_type', sa.String(), nullable=False),
        sa.Column('resource_id', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('role_permission_resources')
