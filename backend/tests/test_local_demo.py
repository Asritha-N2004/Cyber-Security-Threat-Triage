from fastapi.testclient import TestClient
from app.main import app
from test_api import client


def test_local_demo_opens_without_token_and_scopes_identity(client,monkeypatch):
    monkeypatch.setenv('LOCAL_DEMO_MODE','true')
    monkeypatch.setenv('LOCAL_DEMO_ORG_ID','org')
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000)) as local:
        mode=local.get('/api/v1/auth/mode').json()
        assert mode['mode']=='local_demo'
        assert all(user['id']!='outsider' for user in mode['users'])
        assert local.get('/api/v1/me').status_code==200
        assert local.get('/api/v1/reports/performance').status_code==200
        assert local.get('/api/v1/me',headers={'X-Local-Demo-User':'maker'}).json()['role']=='admin'
        assert local.get('/api/v1/me',headers={'X-Local-Demo-User':'outsider'}).status_code==404


def test_demo_never_bypasses_remote_or_foreign_origin_auth(client,monkeypatch):
    monkeypatch.setenv('LOCAL_DEMO_MODE','true')
    monkeypatch.setenv('LOCAL_DEMO_ORG_ID','org')
    with TestClient(app,base_url='http://127.0.0.1',client=('203.0.113.10',50000)) as remote:
        assert remote.get('/api/v1/auth/mode').json()['mode']=='token'
        assert remote.get('/api/v1/me').status_code==401
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000)) as local:
        assert local.post('/api/v1/demo',headers={'Origin':'https://untrusted.example'}).status_code==401
        assert local.get('/api/v1/me',headers={'Host':'untrusted.example'}).status_code==401


def test_token_auth_remains_default(client,monkeypatch):
    monkeypatch.delenv('LOCAL_DEMO_MODE',raising=False)
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000)) as local:
        assert local.get('/api/v1/auth/mode').json()['mode']=='token'
        assert local.get('/api/v1/me').status_code==401
