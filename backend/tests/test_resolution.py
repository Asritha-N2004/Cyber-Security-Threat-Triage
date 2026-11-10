from test_api import client,post_ok


def test_resolution_requires_new_matched_evidence_and_original_anchor(client):
    c,_=client
    source=post_ok(c,'/data/records',json={'name':'Bank','source':'bank','records':[{'transaction_id':'B','date':'2026-01-01','account':'cash','currency':'USD','amount':'100','reference':'REF'}]})
    target=post_ok(c,'/data/records',json={'name':'Ledger','source':'gl','records':[{'transaction_id':'L','date':'2026-01-01','account':'cash','currency':'USD','amount':'90','reference':'REF'}]})
    job=post_ok(c,'/reconciliation',json={'source_id':source['id'],'target_id':target['id']})
    post_ok(c,f'/reconciliation/{job["id"]}/run')
    exception=c.get(f'/api/v1/reconciliation/{job["id"]}/exceptions').json()[0]
    corrected=post_ok(c,'/data/records',json={'name':'Verified ledger','source':'gl','records':[{'transaction_id':'L2','date':'2026-01-01','account':'cash','currency':'USD','amount':'100','reference':'REF'}]})
    verification=post_ok(c,'/reconciliation',json={'source_id':source['id'],'target_id':corrected['id']})
    post_ok(c,f'/reconciliation/{verification["id"]}/run')
    match=c.get(f'/api/v1/reconciliation/{verification["id"]}/matches').json()[0]
    ids=match['evidence']['source_ids']+match['evidence']['target_ids']
    c.headers['Authorization']='Bearer checker'
    assert c.post(f'/api/v1/exceptions/{exception["id"]}/verify-resolution',json={'verified_job_id':verification['id'],'evidence_transaction_ids':ids[:1],'reason':'Partial source evidence is insufficient'}).status_code==409
    result=post_ok(c,f'/exceptions/{exception["id"]}/verify-resolution',json={'verified_job_id':verification['id'],'evidence_transaction_ids':ids,'reason':'Verified corrected ledger against unchanged bank source'})
    assert result['status']=='resolved'
    assert c.get('/api/v1/reports/performance').json()['resolved_exceptions']==1
