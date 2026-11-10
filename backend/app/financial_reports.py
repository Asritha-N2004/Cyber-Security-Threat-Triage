from collections import defaultdict
from decimal import Decimal
from .reconciliation_engine.workflows import field


def accounting_statement(kind,source,target):
    zero=Decimal(0)
    statements={}
    def total(records,currency,side):
        amount=zero
        for record in records:
            if record.currency!=currency:
                continue
            document=field(record,'document_type')
            if kind in ('ap','ar'):
                sign=-1 if document in (('CREDIT_NOTE','CREDIT') if side=='source' else ('REFUND',)) else 1
                amount+=sign*abs(record.amount)
            elif kind=='gateway' and side=='source':
                amount+=(1 if document=='PAYMENT' else -1)*abs(record.amount)
            else:
                amount+=record.amount
        return amount
    for currency in sorted({r.currency for r in source+target}):
        expected=total(source,currency,'source')
        actual=total(target,currency,'target')
        difference=expected+actual if kind=='intercompany' else expected-actual
        statements[currency]={'expected':str(expected),'recorded':str(actual),'difference':str(difference),
            'equation':'source + reciprocal = 0' if kind=='intercompany' else 'expected - recorded = difference'}
    return {'workflow':kind,'balances_by_currency':statements,'basis':'document types and signed canonical records; no FX conversion'}
