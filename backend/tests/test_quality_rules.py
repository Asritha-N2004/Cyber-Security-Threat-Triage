from app.reconciliation_engine.workflows import reconcile_workflow
from app.schemas import Rules
from test_accounting_workflows import tx,categories


def test_cross_identifier_duplicates_remain_visible_not_auto_matched():
    result=reconcile_workflow([tx('s1'),tx('s2')],[tx('t1')],Rules(),'bank')
    assert result['matched_records']==0
    assert 'duplicate_transaction' in categories(result)
    ids={i for e in result['exceptions'] for i in e['evidence']['transaction_ids']}
    assert ids=={'s1','s2','t1'}


def test_explicit_payment_identity_distinguishes_installments():
    source=[tx('s1','100')]
    target=[tx('t1','50',payment_reference='PAY-1'),tx('t2','50',payment_reference='PAY-2')]
    assert reconcile_workflow(source,target,Rules(),'bank')['matched_records']==3


def test_unusual_value_flag_is_evidence_not_fraud_claim():
    source=[tx(f's{i}','10',reference=f'R{i}') for i in range(10)]+[tx('large','10000',reference='BIG')]
    target=[tx(f't{i}','10',reference=f'R{i}') for i in range(10)]+[tx('large-target','10000',reference='BIG')]
    result=reconcile_workflow(source,target,Rules(),'bank')
    assert result['matched_records']==22
    assert 'unusual_transaction_pattern' in categories(result)
    assert all('not proof' in e['evidence']['note'] for e in result['exceptions'])
