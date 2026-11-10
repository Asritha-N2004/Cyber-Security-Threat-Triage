import io
import pytest
from pypdf import PdfReader
from test_api import client,post_ok


@pytest.mark.parametrize('kind,matched,category',[('ap',3,'partial_payment'),('ar',3,'short_payment'),('gateway',5,None),('intercompany',2,'unbalanced_reciprocal'),('gl',3,None)])
def test_specialized_demo_api_and_reports(client,kind,matched,category):
    c,_=client
    job=post_ok(c,'/demo/'+kind)
    assert job['result']['matched_records']==matched
    assert job['result']['workflow']==kind
    report=c.get('/api/v1/reports/reconciliation/'+job['id']).json()
    if category:
        assert category in {e['category'] for e in report['exceptions']}
    response=c.get('/api/v1/reports/reconciliation/'+job['id']+'?format=pdf')
    assert response.status_code==200 and response.content.startswith(b'%PDF')
    reader=PdfReader(io.BytesIO(response.content))
    assert 'Balances by currency' in reader.pages[0].extract_text()
