"""Preserve exact decimal storage on SQLite initialized with the previous schema."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'


def upgrade():
    if op.get_bind().dialect.name == 'sqlite':
        for table in ('imported_transactions', 'reconciliation_exceptions'):
            with op.batch_alter_table(table) as batch:
                batch.alter_column('amount', type_=sa.String(40), existing_type=sa.Numeric(24, 6))


def downgrade():
    raise RuntimeError('Downgrade would risk monetary precision loss; restore a verified backup instead')
