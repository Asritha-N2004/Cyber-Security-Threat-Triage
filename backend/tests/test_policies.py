from app.providers import MockProvider
from app.validation import validate_correction
from test_controls import CONTEXT


def test_closed_period_stale_policy_inactive_account():
    context=CONTEXT|{'posting_date':'2026-01-01','closed_through':'2026-01-31','policy_version':2,
        'accounts':{'fees':{'active':True,'currency':'USD'},'cash':{'active':False,'currency':'USD'}}}
    proposal=MockProvider().propose(context,[])
    result=validate_correction(proposal,context)
    assert not result.passed
    assert any('closed accounting' in f for f in result.findings)
    assert any('inactive' in f for f in result.findings)
    context['closed_through']=None
    context['accounts']['cash']['active']=True
    assert validate_correction(proposal,context).passed
    context['policy_version']=3
    assert not validate_correction(proposal,context).passed
