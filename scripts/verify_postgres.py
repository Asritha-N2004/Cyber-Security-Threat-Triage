"""Explicit synthetic PostgreSQL financial-control integration check for CI/staging."""
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))


def main():
    if os.getenv('RUN_FINANCIAL_SIMULATION_TESTS')!='1' or not os.getenv('DATABASE_URL','').startswith('postgresql'):
        raise SystemExit('Requires a dedicated PostgreSQL test database and RUN_FINANCIAL_SIMULATION_TESTS=1')
    os.environ['EXECUTION_MODE']='simulation'
    os.environ['LLM_PROVIDER']='mock'
    from fastapi.testclient import TestClient
    from app.main import app
    credentials=json.loads((Path(__file__).resolve().parents[1]/'backend'/'.local'/'credentials.json').read_text())
    with TestClient(app) as client:
        client.headers['Authorization']='Bearer '+credentials['analyst']
        def post(path,**kwargs):
            response=client.post('/api/v1'+path,**kwargs)
            assert response.is_success,response.text
            return response.json()
        job=post('/demo')
        assert job['result']['matched_records']>0
        exception=next(e for e in client.get(f'/api/v1/reconciliation/{job["id"]}/exceptions').json() if Decimal(e['amount'])==25)
        proposal=post(f'/exceptions/{exception["id"]}/investigate')
        assert proposal['validation']['passed']
        assert len(client.get(f'/api/v1/exceptions/{exception["id"]}/agents').json())==10
        client.headers['Authorization']='Bearer '+credentials['checker']
        post(f'/corrections/{proposal["id"]}/approve')
        adjustment=post(f'/corrections/{proposal["id"]}/execute',headers={'Idempotency-Key':'pg-control-execute'})
        assert post(f'/corrections/{proposal["id"]}/execute',headers={'Idempotency-Key':'pg-control-execute'})['id']==adjustment['id']
        reversal=post(f'/corrections/{proposal["id"]}/reverse',headers={'Idempotency-Key':'pg-control-reverse'})
        assert reversal['reversal_of']==adjustment['id']
    print('PostgreSQL synthetic integration passed: matching, ten agents, approval, idempotency and reversal.')


if __name__=='__main__':
    main()
