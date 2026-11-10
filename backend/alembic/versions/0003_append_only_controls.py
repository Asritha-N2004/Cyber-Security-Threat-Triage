"""Enforce immutable financial source and evidence tables at the database boundary."""
from alembic import op

revision = '0003'
down_revision = '0002'
TABLES = ('imported_transactions', 'adjustment_entries', 'audit_logs', 'reflection_iterations')


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        for table in TABLES:
            for action in ('UPDATE', 'DELETE'):
                op.execute(f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Append-only record'); END")
    elif dialect == 'postgresql':
        op.execute("CREATE FUNCTION deny_financial_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Append-only record'; END; $$")
        for table in TABLES:
            op.execute(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_financial_mutation()')


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        for table in TABLES:
            for action in ('update', 'delete'):
                op.execute(f'DROP TRIGGER immutable_{table}_{action}')
    elif dialect == 'postgresql':
        for table in TABLES:
            op.execute(f'DROP TRIGGER immutable_{table} ON {table}')
        op.execute('DROP FUNCTION deny_financial_mutation()')
