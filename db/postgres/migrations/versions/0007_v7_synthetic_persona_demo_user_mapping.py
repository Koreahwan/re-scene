"""v7_synthetic_persona_demo_user_mapping

Revision ID: 0007_v7_synthetic_persona_demo_user_mapping
Revises: 0006_v7_synthetic_lab
Create Date: 2026-08-21 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = '0007_v7_synthetic_persona_demo_user_mapping'
down_revision: Union[str, None] = '0006_v7_synthetic_lab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    tables = insp.get_table_names()
    if 'synthetic_personas' in tables:
        columns = [c['name'] for c in insp.get_columns('synthetic_personas')]
        if 'demo_user_id' not in columns:
            with op.batch_alter_table('synthetic_personas') as batch_op:
                batch_op.add_column(sa.Column('demo_user_id', sa.Uuid(), nullable=True))
                batch_op.create_foreign_key(
                    'fk_synthetic_personas_demo_user_id',
                    'users',
                    ['demo_user_id'],
                    ['id'],
                    ondelete='SET NULL'
                )
                batch_op.create_unique_constraint(
                    'uq_synthetic_persona_demo_user_id',
                    ['demo_user_id']
                )
                batch_op.create_index(
                    'ix_synthetic_personas_demo_user_id',
                    ['demo_user_id']
                )
        else:
            # Column already exists (state C: local DB with mutated 0006 applied)
            existing_fks = [fk.get('name') for fk in insp.get_foreign_keys('synthetic_personas')]
            existing_uqs = [uq.get('name') for uq in insp.get_unique_constraints('synthetic_personas')]
            indexes = [idx.get('name') for idx in insp.get_indexes('synthetic_personas')]
            with op.batch_alter_table('synthetic_personas') as batch_op:
                if 'fk_synthetic_personas_demo_user_id' not in existing_fks:
                    batch_op.create_foreign_key(
                        'fk_synthetic_personas_demo_user_id',
                        'users',
                        ['demo_user_id'],
                        ['id'],
                        ondelete='SET NULL'
                    )
                if 'uq_synthetic_persona_demo_user_id' not in existing_uqs:
                    batch_op.create_unique_constraint(
                        'uq_synthetic_persona_demo_user_id',
                        ['demo_user_id']
                    )
                if 'ix_synthetic_personas_demo_user_id' not in indexes:
                    batch_op.create_index(
                        'ix_synthetic_personas_demo_user_id',
                        ['demo_user_id']
                    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    if 'synthetic_personas' in tables:
        columns = [c['name'] for c in insp.get_columns('synthetic_personas')]
        if 'demo_user_id' in columns:
            with op.batch_alter_table('synthetic_personas') as batch_op:
                batch_op.drop_index('ix_synthetic_personas_demo_user_id')
                batch_op.drop_constraint('uq_synthetic_persona_demo_user_id', type_='unique')
                batch_op.drop_constraint('fk_synthetic_personas_demo_user_id', type_='foreignkey')
                batch_op.drop_column('demo_user_id')
