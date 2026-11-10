"""Use indexed-compatible JSONB storage for PostgreSQL evidence structures."""
from alembic import op
from sqlalchemy import JSON,inspect
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base

revision='0009'
down_revision='0008'


def upgrade():
    connection=op.get_bind()
    if connection.dialect.name!='postgresql':
        return
    inspector=inspect(connection)
    for table in Base.metadata.sorted_tables:
        actual={column['name']:column['type'] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if isinstance(column.type,JSON) and not isinstance(actual[column.name],JSONB):
                op.alter_column(table.name,column.name,type_=JSONB(),postgresql_using=f'"{column.name}"::jsonb')


def downgrade():
    raise RuntimeError('Evidence storage downgrade requires an explicit reviewed migration')
