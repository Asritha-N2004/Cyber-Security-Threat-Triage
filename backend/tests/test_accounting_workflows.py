from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.schemas import Rules
from app.reconciliation_engine.workflows import reconcile_workflow


def tx(id,amount='100',reference='INV-1',currency='USD',account='CASH',counterparty='ACME',date='2026-01-01',**business):
    return SimpleNamespace(id=id,amount=Decimal(amount),reference=reference,currency=currency,account=account,
        counterparty=counterparty,date=date,description='',original=business,normalization={},dataset_id='source' if id.startswith('s') else 'target')


def run(source,target,kind,support=None,**rules):
    return reconcile_workflow(source,target,Rules(**rules),kind,support)


def categories(result):
    return {e['category'] for e in result['exceptions']}


def test_ap_three_way_and_po_controls():
    invoice=tx('s1',po_id='PO-1')
    po=tx('po',po_id='PO-1')
    payments=[tx('p1','40'),tx('p2','60')]
    assert run([invoice],payments,'ap',[po])['matched_records']==3
    assert 'missing_purchase_order' in categories(run([invoice],payments,'ap'))
    assert 'purchase_order_amount_mismatch' in categories(run([invoice],payments,'ap',[tx('po','99',po_id='PO-1')]))
    assert 'partial_payment' in categories(run([invoice],payments[:1],'ap',[po]))
    assert 'overpayment' in categories(run([invoice],[tx('p','101')],'ap',[po]))


def test_duplicate_invoice_not_allocated():
    result=run([tx('s1'),tx('s2')],[tx('p')],'ar')
    assert result['matched_records']==0 and 'duplicate_invoice' in categories(result)


def test_ar_credit_allocation_refund_and_unallocated():
    source=[tx('s1'),tx('scredit','20',document_type='CREDIT_NOTE')]
    assert run(source,[tx('receipt','80')],'ar')['matched_records']==3
    assert 'short_payment' in categories(run(source,[tx('receipt','70')],'ar'))
    assert 'overpayment' in categories(run(source,[tx('receipt','90')],'ar'))
    assert run(source,[tx('receipt','100'),tx('refund','20',document_type='REFUND')],'ar')['matched_records']==4
    assert 'unallocated_receipt' in categories(run(source,[tx('receipt','80'),tx('orphan','10',reference='OTHER')],'ar'))
    assert 'currency_mismatch' in categories(run(source,[tx('receipt','80',currency='EUR')],'ar'))


def test_gateway_gross_to_net_fee_refund_chargeback():
    source=[tx('s1','100',batch_id='B1',document_type='PAYMENT',expected_fee='3'),
        tx('s2','20',batch_id='B1',document_type='REFUND'),tx('s3','10',batch_id='B1',document_type='CHARGEBACK'),
        tx('s4','3',batch_id='B1',document_type='FEE')]
    assert run(source,[tx('deposit','67',batch_id='B1')],'gateway')['matched_records']==5
    assert 'settlement_discrepancy' in categories(run(source,[tx('deposit','66',batch_id='B1')],'gateway'))
    assert 'settlement_delay' in categories(run(source,[tx('deposit','67',batch_id='B1',date='2026-02-01')],'gateway'))
    assert 'missing_settlement' in categories(run(source,[],'gateway'))
    source[0].original['expected_fee']='4'
    assert 'fee_discrepancy' in categories(run(source,[tx('deposit','67',batch_id='B1')],'gateway'))


def test_intercompany_requires_reciprocal_entities_and_sign():
    source=[tx('s1','100',entity_id='A',counterparty_entity='B')]
    target=[tx('t1','-100',entity_id='B',counterparty_entity='A')]
    assert run(source,target,'intercompany')['matched_records']==2
    assert 'unbalanced_reciprocal' in categories(run(source,[tx('t1','100',entity_id='B',counterparty_entity='A')],'intercompany'))
    assert 'counterparty_mismatch' in categories(run(source,[tx('t1','-100',entity_id='C',counterparty_entity='A')],'intercompany'))
    assert 'currency_mismatch' in categories(run(source,[tx('t1','-100',entity_id='B',counterparty_entity='A',currency='EUR')],'intercompany'))


def test_gl_mapping_balances_and_journal_invariants():
    source=[tx('s1','60',reference='ONE',account='SUB'),tx('s2','40',reference='TWO',account='SUB')]
    assert run(source,[tx('gl','100',account='CONTROL')],'gl',account_mapping={'SUB':'CONTROL'})['matched_records']==3
    assert 'balance_difference' in categories(run(source,[tx('gl','99',account='CONTROL')],'gl',account_mapping={'SUB':'CONTROL'}))
    result=run([tx('s1','100',journal_id='J1',account='CASH'),tx('s2','-99',journal_id='J1',account='PAYABLE')],[],'gl')
    assert 'unbalanced_journal' in categories(result)
    result=run([tx('s1'),tx('s2')],[tx('t','200')],'gl')
    assert categories(result)&{'duplicate_posting','duplicate_transaction'}


@pytest.mark.parametrize('kind',['ap','ar','gateway','intercompany','gl'])
def test_workflow_coverage(kind):
    result=run([tx('s')],[tx('t',reference='OTHER')],kind)
    matched={i for m in result['matches'] for i in m['source_ids']+m['target_ids']}
    explained={i for e in result['exceptions'] for i in e['evidence']['transaction_ids']}
    assert matched|explained=={'s','t'}
    assert not matched&explained
