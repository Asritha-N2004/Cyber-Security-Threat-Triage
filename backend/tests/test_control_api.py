from datetime import timedelta
from sqlalchemy import select
from test_api import client,post_ok,fee_proposal
from app.models_extended import AgentExecution,WorkflowCheckpoint,Task,TokenGrant
from app.worker import process_one
from app.database import now


def test_agent_history_checkpoints_and_tenant_scope(client):
    c,factory=client
    _,exception,proposal=fee_proposal(c)
    events=c.get(f'/api/v1/exceptions/{exception["id"]}/agents').json()
    assert len(events)==10 and len({e['agent'] for e in events})==10
    checkpoints=c.get(f'/api/v1/exceptions/{exception["id"]}/checkpoints').json()
    assert checkpoints[-1]['next_node']=='complete'
    assert 'state' not in checkpoints[0]
    c.headers['Authorization']='Bearer outsider'
    assert c.get(f'/api/v1/exceptions/{exception["id"]}/agents').status_code==404


def test_policy_change_invalidates_approval_and_closed_period(client):
    c,_=client
    _,_,proposal=fee_proposal(c)
    policy=c.get('/api/v1/settings/policy').json()
    post_ok(c,'/settings/policy',json=policy['settings']|{'closed_through':'2099-12-31'})
    c.headers['Authorization']='Bearer checker'
    assert c.post(f'/api/v1/corrections/{proposal["id"]}/approve').status_code==409
    checked=post_ok(c,f'/corrections/{proposal["id"]}/validate')
    assert any('closed accounting' in message for message in checked['validation']['findings'])
    assert any('stale' in message for message in checked['validation']['findings'])


def test_durable_task_worker_and_idempotent_enqueue(client):
    c,factory=client
    job=post_ok(c,'/demo')
    task=post_ok(c,'/tasks',json={'kind':'reconciliation','resource_id':job['id']})
    assert post_ok(c,'/tasks',json={'kind':'reconciliation','resource_id':job['id']})['id']==task['id']
    assert process_one(factory)['status']=='completed'
    assert c.get(f'/api/v1/tasks/{task["id"]}').json()['status']=='completed'
    assert process_one(factory) is None
    exception=c.get(f'/api/v1/reconciliation/{job["id"]}/exceptions').json()[0]
    post_ok(c,'/tasks',json={'kind':'investigation','resource_id':exception['id']})
    assert process_one(factory)['status']=='completed'


def test_token_rotation_revokes_previous_token(client):
    c,factory=client
    rotated=post_ok(c,'/auth/rotate')
    assert c.get('/api/v1/me').status_code==401
    c.headers['Authorization']='Bearer '+rotated['access_token']
    assert c.get('/api/v1/me').status_code==200
    with factory() as db:
        grant=db.scalar(select(TokenGrant))
        grant.expires_at=now()-timedelta(seconds=1)
        db.commit()
    assert c.get('/api/v1/me').status_code==401


def test_abandoned_worker_lease_exhaustion_escalates(client):
    c,factory=client
    job=post_ok(c,'/demo')
    task=post_ok(c,'/tasks',json={'kind':'reconciliation','resource_id':job['id']})
    with factory() as db:
        record=db.get(Task,task['id'])
        record.status='running'
        record.attempts=3
        record.lease_until=now()-timedelta(seconds=1)
        db.commit()
    assert process_one(factory) is None
    result=c.get(f'/api/v1/tasks/{task["id"]}').json()
    assert result['status']=='failed' and result['result']['manual_escalation']
