from test_api import client,post_ok


def test_reviewed_holdout_training_versioning_and_constraints(client):
    c,_=client
    jobs=[]
    for index in range(2):
        job=post_ok(c,'/demo')
        jobs.append(job)
        matches=c.get(f'/api/v1/reconciliation/{job["id"]}/matches').json()
        for number,match in enumerate(matches[:8]):
            post_ok(c,f'/matches/{match["id"]}/review',json={'decision':'accept' if number%2 else 'reject','reason':'Independent synthetic review fixture'})
    response=c.post('/api/v1/ml/train',json={'train_job_ids':[jobs[0]['id']],'test_job_ids':[jobs[0]['id']]})
    assert response.status_code==422
    artifact=post_ok(c,'/ml/train',json={'train_job_ids':[jobs[0]['id']],'test_job_ids':[jobs[1]['id']],'kind':'logistic'})
    assert artifact['metrics']['training_pairs']==8 and not artifact['metrics']['calibrated']
    match=c.get(f'/api/v1/reconciliation/{jobs[1]["id"]}/matches').json()[0]
    result=post_ok(c,f'/ml/models/{artifact["id"]}/rank',json={'source_transaction_id':match['evidence']['source_ids'][0],
        'target_transaction_ids':match['evidence']['target_ids']})
    assert not result['candidates'][0]['match_accepted']
    assert result['candidates'][0]['deterministic_eligible']
    c.headers['Authorization']='Bearer outsider'
    assert c.get('/api/v1/ml/models').json()==[]
    assert c.post(f'/api/v1/ml/models/{artifact["id"]}/rank',json={'source_transaction_id':'unknown','target_transaction_ids':['other']}).status_code==404
