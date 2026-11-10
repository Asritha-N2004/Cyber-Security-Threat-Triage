from decimal import Decimal
from sqlalchemy import select
from app.database import Base, Dataset, Organization, Transaction, make_engine
from app.ingestion import ingest
from sqlalchemy.orm import Session


def test_sqlite_exact_large_decimal_roundtrip(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path / "precision.db"}')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id='org', name='Test'))
        db.flush()
        ingest(db, 'org', 'precision', 'bank', [{'transaction_id':'large','date':'2026-01-01','currency':'USD','account':'cash','amount':'99999999999999999.99'}])
        db.commit()
    with Session(engine) as db:
        assert db.scalar(select(Transaction.amount)) == Decimal('99999999999999999.99')
    engine.dispose()
