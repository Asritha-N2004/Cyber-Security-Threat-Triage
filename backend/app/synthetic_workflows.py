"""Clearly synthetic business documents, without ground-truth labels in model inputs."""


def record(identifier,amount,reference='INV-1',**extra):
    return {'transaction_id':identifier,'date':'2026-01-15','amount':str(amount),'account':'cash','currency':'USD',
        'reference':reference,'counterparty':'Synthetic Acme','description':'Synthetic accounting document',**extra}


def generate_workflow(kind):
    if kind=='ap':
        return ([record('I1','100',po_id='PO-1',document_type='INVOICE'),record('I2','200','INV-2',po_id='PO-2',document_type='INVOICE')],
            [record('P1','40',document_type='PAYMENT'),record('P2','60',document_type='PAYMENT'),record('P3','150','INV-2',document_type='PAYMENT')],
            [record('PO1','100','PO-1',po_id='PO-1',document_type='PURCHASE_ORDER'),record('PO2','200','PO-2',po_id='PO-2',document_type='PURCHASE_ORDER')])
    if kind=='ar':
        return ([record('I1','100',document_type='INVOICE'),record('C1','20',document_type='CREDIT_NOTE'),record('I2','200','INV-2',document_type='INVOICE')],
            [record('R1','80',document_type='RECEIPT'),record('R2','180','INV-2',document_type='RECEIPT'),record('R3','15','UNKNOWN',document_type='RECEIPT')],[])
    if kind=='gateway':
        return ([record('PAY','100','BATCH-1',batch_id='BATCH-1',document_type='PAYMENT',expected_fee='3'),
            record('REF','20','BATCH-1',batch_id='BATCH-1',document_type='REFUND'),record('CB','10','BATCH-1',batch_id='BATCH-1',document_type='CHARGEBACK'),
            record('FEE','3','BATCH-1',batch_id='BATCH-1',document_type='FEE')],[record('DEP','67','BATCH-1',batch_id='BATCH-1',document_type='SETTLEMENT')],[])
    if kind=='intercompany':
        return ([record('A1','100',entity_id='ENTITY-A',counterparty_entity='ENTITY-B'),record('A2','200','IC-2',entity_id='ENTITY-A',counterparty_entity='ENTITY-B')],
            [record('B1','-100',entity_id='ENTITY-B',counterparty_entity='ENTITY-A'),record('B2','-190','IC-2',entity_id='ENTITY-B',counterparty_entity='ENTITY-A')],[])
    if kind=='gl':
        return ([record('SUB1','60','REF-1',account='SUB'),record('SUB2','40','REF-2',account='SUB')],
            [record('GL1','100','CONTROL',account='CONTROL')],[])
    raise ValueError('Supported specialized demos: ap, ar, gateway, intercompany, gl')
