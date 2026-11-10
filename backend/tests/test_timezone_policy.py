from test_api import client,post_ok


def test_tenant_timezone_is_applied_and_preserved_for_independent_checks(client):
    c,_=client
    policy=c.get('/api/v1/settings/policy').json()
    post_ok(c,'/settings/policy',json=policy['settings']|{'source_timezone':'Asia/Kolkata'})
    record={'transaction_id':'TZ','date':'2026-01-01T00:30:00','currency':'USD','account':'cash','amount':'1.00'}
    preview=post_ok(c,'/data/preview',json={'records':[record]})
    assert preview['preview'][0]['normalized']['date']=='2025-12-31'
    dataset=post_ok(c,'/data/records',json={'name':'Timezone','source':'bank','records':[record]})
    row=c.get(f'/api/v1/data/datasets/{dataset["id"]}/transactions').json()[0]
    assert row['date']=='2025-12-31' and row['original']['date']=='2026-01-01T00:30:00'
    assert row['normalization']['source_timezone']=='Asia/Kolkata'
