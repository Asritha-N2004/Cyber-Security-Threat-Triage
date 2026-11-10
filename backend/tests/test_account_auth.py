from fastapi.testclient import TestClient
from app.main import app
from app.models_extended import LoginAccount
from test_api import client


def test_signup_login_logout_isolation_and_simple_password(client,monkeypatch):
    _,factory=client
    monkeypatch.setenv('ACCOUNT_LOGIN_MODE','true')
    monkeypatch.setenv('HOSTED_DEMO_MODE','true')
    with TestClient(app,base_url='https://accounts.example') as first,TestClient(app,base_url='https://accounts.example') as second:
        assert first.get('/api/v1/auth/mode').json()['mode']=='account'
        assert first.get('/api/v1/me').status_code==401
        response=first.post('/api/v1/auth/register',json={'username':'simple name','password':'abcdef'})
        assert response.status_code==201,response.text
        assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
        user=first.get('/api/v1/me').json()
        assert user['name']=='simple name'
        with factory() as db:
            account=db.get(LoginAccount,user['id'])
            assert 'abcdef' not in account.password_hash
        assert second.post('/api/v1/auth/register',json={'username':'SIMPLE NAME','password':'abcdef'}).status_code==409
        assert second.post('/api/v1/auth/login',json={'username':'simple name','password':'wrong'}).status_code==401
        assert second.post('/api/v1/auth/register',json={'username':'someone else','password':'123456'}).status_code==201
        assert second.get('/api/v1/me').json()['org_id']!=user['org_id']
        old_cookie=first.cookies.get('reconcile_session')
        assert first.post('/api/v1/auth/logout').status_code==200
        assert first.get('/api/v1/me').status_code==401
        first.cookies.set('reconcile_session',old_cookie)
        assert first.get('/api/v1/me').status_code==401
        first.cookies.clear()
        assert first.post('/api/v1/auth/login',json={'username':' SIMPLE NAME ','password':'abcdef'}).status_code==200
        assert first.get('/api/v1/me').json()['id']==user['id']


def test_signup_minimum_and_origin(client):
    c,_=client
    assert c.post('/api/v1/auth/register',json={'username':'  ','password':'abcdef'}).status_code==422
    assert c.post('/api/v1/auth/register',json={'username':'name','password':'12345'}).status_code==422
    assert c.post('/api/v1/auth/register',json={'username':'name','password':'abcdef'},headers={'Origin':'https://untrusted.example'}).status_code==403
