"""add rbac models

Revision ID: add_rbac_models
Revises: 
Create Date: 2026-02-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'add_rbac_models'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table('organizations'):
        op.create_table(
            'organizations',
            sa.Column('id', sa.String(), primary_key=True, nullable=False),
            sa.Column('name', sa.String(), nullable=False, unique=True),
        )

    if not inspector.has_table('roles'):
        op.create_table(
            'roles',
            sa.Column('id', sa.String(), primary_key=True, nullable=False),
            sa.Column('name', sa.String(), nullable=False, unique=True),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('is_global', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        )

    if not inspector.has_table('permissions'):
        op.create_table(
            'permissions',
            sa.Column('id', sa.String(), primary_key=True, nullable=False),
            sa.Column('codename', sa.String(), nullable=False, unique=True),
            sa.Column('description', sa.String(), nullable=True),
        )

    if not inspector.has_table('role_permissions'):
        op.create_table(
            'role_permissions',
            sa.Column('id', sa.String(), primary_key=True, nullable=False),
            sa.Column('role_id', sa.String(), sa.ForeignKey('roles.id'), nullable=False),
            sa.Column('permission_id', sa.String(), sa.ForeignKey('permissions.id'), nullable=False),
        )

    if not inspector.has_table('user_organization_roles'):
        op.create_table(
            'user_organization_roles',
            sa.Column('id', sa.String(), primary_key=True, nullable=False),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('organization_id', sa.String(), sa.ForeignKey('organizations.id'), nullable=True),
            sa.Column('role_id', sa.String(), sa.ForeignKey('roles.id'), nullable=False),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('user_organization_roles'):
        op.drop_table('user_organization_roles')

    if inspector.has_table('role_permissions'):
        op.drop_table('role_permissions')

    if inspector.has_table('permissions'):
        op.drop_table('permissions')

    if inspector.has_table('roles'):
        op.drop_table('roles')

    if inspector.has_table('organizations'):
        op.drop_table('organizations')
