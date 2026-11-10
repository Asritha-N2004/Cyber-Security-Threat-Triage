from test_api import client,post_ok


def test_rejection_releases_membership_and_acceptance_restores_counts(client):
    c,_=client
    job=post_ok(c,'/demo')
    match=c.get(f'/api/v1/reconciliation/{job["id"]}/matches').json()[0]
    count=job['result']['matched_records']
    post_ok(c,f'/matches/{match["id"]}/review',json={'decision':'reject','reason':'Ambiguous supporting reference needs review'})
    assert c.get(f'/api/v1/reconciliation/{job["id"]}').json()['result']['matched_records']==count-2
    post_ok(c,f'/matches/{match["id"]}/review',json={'decision':'accept','reason':'Reference verified against authoritative evidence'})
    assert c.get(f'/api/v1/reconciliation/{job["id"]}').json()['result']['matched_records']==count


def test_manual_match_cannot_double_consume_transactions(client):
    c,_=client
    job=post_ok(c,'/demo')
    match=c.get(f'/api/v1/reconciliation/{job["id"]}/matches').json()[0]
    body={'source_ids':match['evidence']['source_ids'],'target_ids':match['evidence']['target_ids'],'reason':'Manual authoritative record review'}
    assert c.post(f'/api/v1/reconciliation/{job["id"]}/manual-match',json=body).status_code==409
    post_ok(c,f'/matches/{match["id"]}/review',json={'decision':'reject','reason':'Release the original match for independent review'})
    post_ok(c,f'/reconciliation/{job["id"]}/manual-match',json=body)
    assert c.post(f'/api/v1/matches/{match["id"]}/review',json={'decision':'accept','reason':'Attempt duplicate transaction consumption'}).status_code==409
