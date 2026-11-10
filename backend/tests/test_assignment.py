from test_api import client,post_ok


def test_investigator_assignment_stays_in_tenant(client):
    c,_=client
    job=post_ok(c,'/demo')
    exception=c.get(f'/api/v1/reconciliation/{job["id"]}/exceptions').json()[0]
    assert c.post(f'/api/v1/exceptions/{exception["id"]}/assign',json={'assigned_user_id':'outsider'}).status_code==404
    assigned=post_ok(c,f'/exceptions/{exception["id"]}/assign',json={'assigned_user_id':'maker'})
    assert assigned['assigned_user_id']=='maker'
    assert all(u['id']!='outsider' for u in c.get('/api/v1/users').json())
