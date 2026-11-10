from fastapi.testclient import TestClient
from app.main import app
from test_api import client


def test_hosted_demo_uses_private_cookie_scoped_workspaces(client,monkeypatch):
    monkeypatch.setenv('HOSTED_DEMO_MODE','true')
    monkeypatch.setenv('HOSTED_DEMO_SECRET','offline-test-signing-key-at-least-thirty-two-characters')
    with TestClient(app,base_url='https://demo.example') as first,TestClient(app,base_url='https://demo.example') as second:
        assert first.get('/api/v1/me').status_code==401
        response=first.get('/api/v1/auth/mode')
        mode=response.json()
        assert mode['mode']=='hosted_demo'
        assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
        assert first.get('/api/v1/me').json()['name']=='analyst'
        other=second.get('/api/v1/auth/mode').json()
        assert set(u['id'] for u in mode['users']).isdisjoint(u['id'] for u in other['users'])
        first.headers['X-Local-Demo-User']=other['default_user_id']
        assert first.get('/api/v1/me').status_code==401
        first.headers.pop('X-Local-Demo-User')
        assert first.post('/api/v1/demo').status_code==201
        assert second.get('/api/v1/reconciliation').json()==[]
        job=first.get('/api/v1/reconciliation').json()[0]
        exceptions=first.get(f"/api/v1/reconciliation/{job['id']}/exceptions").json()
        task=first.post('/api/v1/tasks',json={'kind':'investigation','resource_id':exceptions[0]['id']})
        assert task.status_code==202 and task.json()['status']=='completed'


def test_hosted_demo_rejects_forged_or_expired_cookie(client,monkeypatch):
    monkeypatch.setenv('HOSTED_DEMO_MODE','true')
    monkeypatch.setenv('HOSTED_DEMO_SECRET','offline-test-signing-key-at-least-thirty-two-characters')
    from app.hosted_demo import decode_cookie
    assert decode_cookie('invalid.forged') is None
    with TestClient(app,base_url='https://demo.example') as browser:
        browser.get('/api/v1/auth/mode')
        value=browser.cookies.get('reconcile_demo')
        assert decode_cookie(value)
        monkeypatch.setenv('HOSTED_DEMO_SECRET','different-test-signing-key-at-least-thirty-two-characters')
        assert decode_cookie(value) is None
        assert browser.get('/api/v1/me').status_code==401
