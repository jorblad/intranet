"""add organization fk to terms/programs/schedules

Revision ID: add_org_fk_taxonomy
Revises: add_rbac_models
Create Date: 2026-02-09 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'add_org_fk_taxonomy'
down_revision = 'add_rbac_models'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    # terms.organization_id
    if inspector.has_table('terms'):
        term_cols = [c['name'] for c in inspector.get_columns('terms')]
        if 'organization_id' not in term_cols:
            op.add_column('terms', sa.Column('organization_id', sa.String(), nullable=True))
            op.create_foreign_key('fk_terms_organization', 'terms', 'organizations', ['organization_id'], ['id'])

    # programs.organization_id
    if inspector.has_table('programs'):
        prog_cols = [c['name'] for c in inspector.get_columns('programs')]
        if 'organization_id' not in prog_cols:
            op.add_column('programs', sa.Column('organization_id', sa.String(), nullable=True))
            op.create_foreign_key('fk_programs_organization', 'programs', 'organizations', ['organization_id'], ['id'])

    # schedules.organization_id
    if inspector.has_table('schedules'):
        sched_cols = [c['name'] for c in inspector.get_columns('schedules')]
        if 'organization_id' not in sched_cols:
            op.add_column('schedules', sa.Column('organization_id', sa.String(), nullable=True))
            op.create_foreign_key('fk_schedules_organization', 'schedules', 'organizations', ['organization_id'], ['id'])


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('schedules'):
        sched_cols = [c['name'] for c in inspector.get_columns('schedules')]
        if 'organization_id' in sched_cols:
            op.drop_constraint('fk_schedules_organization', 'schedules', type_='foreignkey')
            op.drop_column('schedules', 'organization_id')

    if inspector.has_table('programs'):
        prog_cols = [c['name'] for c in inspector.get_columns('programs')]
        if 'organization_id' in prog_cols:
            op.drop_constraint('fk_programs_organization', 'programs', type_='foreignkey')
            op.drop_column('programs', 'organization_id')

    if inspector.has_table('terms'):
        term_cols = [c['name'] for c in inspector.get_columns('terms')]
        if 'organization_id' in term_cols:
            op.drop_constraint('fk_terms_organization', 'terms', type_='foreignkey')
            op.drop_column('terms', 'organization_id')
