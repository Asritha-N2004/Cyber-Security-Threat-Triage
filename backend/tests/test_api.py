import io
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select
from app.database import Base, Organization, User, Transaction, Adjustment, Audit, make_engine, get_db
from app.main import app
from app.security import token_hash
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = make_engine(f'sqlite:///{tmp_path / "test.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        for org_id in ('org', 'other'):
            db.add(Organization(id=org_id, name=org_id))
        db.flush()
        for name, role, org in [('maker', 'admin', 'org'), ('checker', 'approver', 'org'), ('checker2', 'approver', 'org'), ('outsider', 'admin', 'other')]:
            db.add(User(id=name, org_id=org, name=name, role=role, token_hash=token_hash(name)))
        db.commit()
    def db_override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setenv('RATE_LIMIT_PER_MINUTE', '10000')
    monkeypatch.setenv('ALLOW_LEGACY_TOKENS','true')
    with TestClient(app) as c:
        c.headers['Authorization'] = 'Bearer maker'
        yield c, factory
    app.dependency_overrides.clear()
    engine.dispose()


def post_ok(c, url, **kwargs):
    response = c.post('/api/v1' + url, **kwargs)
    assert response.is_success, response.text
    return response.json()


def fee_proposal(c):
    job = post_ok(c, '/demo')
    exceptions = c.get(f'/api/v1/reconciliation/{job["id"]}/exceptions').json()
    fee = next(e for e in exceptions if e['category'] == 'unmatched_source' and __import__('decimal').Decimal(e['amount']) == 25)
    proposal = post_ok(c, f'/exceptions/{fee["id"]}/investigate')
    return job, fee, proposal


def test_full_workflow_controls_idempotency_reversal(client, monkeypatch):
    c, factory = client
    job, fee, p = fee_proposal(c)
    assert p['validation']['passed'] and p['content']['action'] == 'draft_journal'
    assert c.post(f'/api/v1/corrections/{p["id"]}/approve').status_code == 403
    c.headers['Authorization'] = 'Bearer checker'
    post_ok(c, f'/corrections/{p["id"]}/approve')
    assert c.post(f'/api/v1/corrections/{p["id"]}/execute', headers={'Idempotency-Key': 'execute-01'}).status_code == 403
    monkeypatch.setenv('EXECUTION_MODE', 'simulation')
    adjustment = post_ok(c, f'/corrections/{p["id"]}/execute', headers={'Idempotency-Key': 'execute-01'})
    report = c.get(f'/api/v1/reports/reconciliation/{job["id"]}').json()
    assert __import__('decimal').Decimal(report['simulation_by_currency']['USD']['simulated_cash_adjustment']) == -25
    assert post_ok(c, f'/corrections/{p["id"]}/execute', headers={'Idempotency-Key': 'execute-01'})['id'] == adjustment['id']
    assert c.post(f'/api/v1/corrections/{p["id"]}/execute', headers={'Idempotency-Key': 'execute-02'}).status_code == 409
    reversal = post_ok(c, f'/corrections/{p["id"]}/reverse', headers={'Idempotency-Key': 'reverse-01'})
    assert reversal['reversal_of'] == adjustment['id']
    report = c.get(f'/api/v1/reports/reconciliation/{job["id"]}').json()
    assert __import__('decimal').Decimal(report['simulation_by_currency']['USD']['simulated_cash_adjustment']) == 0
    assert post_ok(c, f'/corrections/{p["id"]}/reverse', headers={'Idempotency-Key': 'reverse-01'})['id'] == reversal['id']
    assert c.get(f'/api/v1/exceptions/{fee["id"]}').json()['status'] == 'open'
    with factory() as db:
        assert len(list(db.scalars(select(Adjustment)))) == 2
        original = db.scalar(select(Transaction).where(Transaction.external_id == 'FEE'))
        assert original.amount == __import__('decimal').Decimal('-25')
        original.amount = 0
        with pytest.raises(ValueError, match='Append-only'):
            db.commit()
    assert len(c.get('/api/v1/audit').json()) >= 6
    assert c.get(f'/api/v1/reports/reconciliation/{job["id"]}?format=csv').headers['content-type'].startswith('text/csv')


def test_tenant_isolation_auth_and_repeat_run(client):
    c, _ = client
    job = post_ok(c, '/demo')
    before = c.get(f'/api/v1/reconciliation/{job["id"]}/matches').json()
    post_ok(c, f'/reconciliation/{job["id"]}/run')
    assert c.get(f'/api/v1/reconciliation/{job["id"]}/matches').json() == before
    c.headers['Authorization'] = 'Bearer outsider'
    assert c.get(f'/api/v1/reconciliation/{job["id"]}').status_code == 404
    assert c.get(f'/api/v1/data/datasets/{job["source_id"]}/transactions').status_code == 404
    assert c.get('/api/v1/exceptions').json() == []
    c.headers.clear()
    assert c.get('/api/v1/audit').status_code == 401


def test_csv_excel_json_partial_import(client):
    c, _ = client
    csv = b'transaction_id,date,account,currency,amount\na,2026-01-01,cash,USD,0.30\na,2026-01-01,cash,USD,0.30\nb,broken,cash,USD,1\n'
    dataset = post_ok(c, '/data/upload', files={'file': ('bank.csv', csv)}, data={'source': 'bank'})
    assert dataset['quality']['accepted'] == 1 and dataset['quality']['rejected'] == 2
    assert dataset['quality']['errors'][0]['original']['transaction_id'] == 'a'
    workbook = Workbook()
    workbook.active.append(['transaction_id', 'date', 'account', 'currency', 'amount'])
    workbook.active.append(['excel', '2026-01-01', 'cash', 'USD', '0.30'])
    output = io.BytesIO()
    workbook.save(output)
    dataset = post_ok(c, '/data/upload', files={'file': ('ledger.xlsx', output.getvalue())}, data={'source': 'ledger'})
    assert dataset['quality']['accepted'] == 1
    dataset = post_ok(c, '/data/upload', files={'file': ('ledger.json', b'[{"transaction_id":"j","date":"2026-01-01","account":"cash","currency":"USD","amount":0.3}]')}, data={'source': 'ledger'})
    assert dataset['quality']['accepted'] == 1
    assert c.post('/api/v1/data/upload', files={'file': ('bad.exe', b'bad')}, data={'source': 'bank'}).status_code == 422


def test_dual_approval_and_manual_review(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv('DUAL_APPROVAL_THRESHOLD', '20')
    monkeypatch.setenv('EXECUTION_MODE', 'simulation')
    _, _, p = fee_proposal(c)
    c.headers['Authorization'] = 'Bearer checker'
    assert post_ok(c, f'/corrections/{p["id"]}/approve')['status'] == 'validated'
    assert post_ok(c, f'/corrections/{p["id"]}/approve')['status'] == 'validated'
    assert c.post(f'/api/v1/corrections/{p["id"]}/execute', headers={'Idempotency-Key': 'execute-01'}).status_code == 409
    c.headers['Authorization'] = 'Bearer checker2'
    assert post_ok(c, f'/corrections/{p["id"]}/approve')['status'] == 'approved'
    post_ok(c, f'/corrections/{p["id"]}/execute', headers={'Idempotency-Key': 'execute-01'})
