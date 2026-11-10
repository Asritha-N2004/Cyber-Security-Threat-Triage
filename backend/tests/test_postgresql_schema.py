from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.database import Match,Transaction


def test_postgres_ddl_uses_jsonb_and_numeric():
    match=str(CreateTable(Match.__table__).compile(dialect=postgresql.dialect()))
    transaction=str(CreateTable(Transaction.__table__).compile(dialect=postgresql.dialect()))
    assert 'JSONB' in match
    assert 'NUMERIC(24, 6)' in transaction
