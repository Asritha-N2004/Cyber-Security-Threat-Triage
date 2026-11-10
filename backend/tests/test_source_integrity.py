from app.agents.specialists import IndependentValidationAgent
from app.providers import MockProvider
from test_controls import CONTEXT


def test_independent_validator_recalculates_canonical_record_from_source():
    raw={'transaction_id':'bank-fee','date':'2026-01-01','account':'cash','currency':'USD','amount':'-25','reference':'FEE'}
    record={'id':'bank-fee','date':'2026-01-01','account':'CASH','currency':'USD','amount':'-99','reference':'FEE','original':raw}
    context=CONTEXT|{'records':[record]}
    proposal=MockProvider().propose(context,[])
    output=IndependentValidationAgent().run(context,{'proposal':proposal.model_dump(mode='json')})
    assert not output.facts['validation']['passed']
    assert any('independently normalized' in f for f in output.findings)
