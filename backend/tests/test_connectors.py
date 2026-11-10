from sqlalchemy import create_engine,text
from test_api import client,post_ok


def test_readonly_database_import_and_mapping_preview(client,tmp_path,monkeypatch):
    c,_=client
    url=f'sqlite:///{tmp_path / "external.db"}'
    engine=create_engine(url)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE reconciliation_export (transaction_id TEXT, date TEXT, currency TEXT, account TEXT, amount TEXT)'))
        connection.execute(text("INSERT INTO reconciliation_export VALUES ('EXT-1','2026-01-01','USD','cash','12.30')"))
    engine.dispose()
    monkeypatch.setenv('FINANCIAL_SOURCE_DATABASE_URL',url)
    result=post_ok(c,'/integrations/database/import',json={'name':'External database fixture','mapping':{}})
    assert result['quality']['accepted']==1
    rows=[{'id':'p','date':'2026-01-01','currency':'USD','account':'cash','amount':'1.00'}]
    preview=post_ok(c,'/data/preview',json={'records':rows,'mapping':{'id':'transaction_id'}})
    assert preview['preview'][0]['valid'] and not preview['persisted']
    assert len(c.get('/api/v1/data/datasets').json())==1


def test_http_requires_operator_https_configuration(client,monkeypatch):
    c,_=client
    monkeypatch.setenv('FINANCIAL_SOURCE_URL','http://127.0.0.1/admin')
    assert c.post('/api/v1/integrations/http/import',json={'name':'blocked','mapping':{}}).status_code==422
