"""Accounting-specific deterministic workflows.

Invoice references, entity identities and batch IDs are explicit source evidence.
Descriptions never authorize allocations, currency conversions or postings.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from .transaction_matcher import reconcile

VERSION = 'accounting-v2'
ZERO = Decimal(0)


def business(record):
    return getattr(record, 'normalization', {}).get('business', getattr(record, 'original', {}))


def field(record, name, default=''):
    value = business(record).get(name, default)
    return str(value or '').strip().upper()


def reference(record):
    return field(record, 'invoice_id') or record.reference


class Outcome:
    def __init__(self, source, target, kind):
        self.source, self.target, self.kind = source, target, kind
        self.matches, self.exceptions = [], []
        self.used, self.explained = set(), set()

    def issue(self, category, records, amount=None, evidence=None):
        if not records:
            return
        ids = list(dict.fromkeys(r.id for r in records))
        currencies = {r.currency for r in records}
        # No mixed-currency exposure is represented as a sum.
        involved = abs(records[0].amount) if amount is None else abs(amount)
        self.exceptions.append({'category': category, 'severity': 'high' if category in
            ('currency_mismatch', 'duplicate_invoice', 'unbalanced_journal', 'counterparty_mismatch') or involved >= 10000 else 'medium',
            'amount': str(involved), 'currency': records[0].currency,
            'evidence': {'transaction_ids': ids, 'workflow': self.kind, 'rule_version': VERSION,
                'currencies': sorted(currencies), **(evidence or {})}})
        self.explained.update(ids)

    def match(self, left, right, evidence=None):
        ids = [r.id for r in left + right]
        if len(set(ids)) != len(ids) or self.used.intersection(ids):
            raise ValueError('Workflow attempted to consume a transaction twice')
        self.used.update(ids)
        self.matches.append({'kind': self.kind, 'source_ids': [r.id for r in left], 'target_ids': [r.id for r in right],
            'amount_difference': '0', 'rule_version': VERSION, **(evidence or {})})

    def finish(self):
        for side, records in [('source', self.source), ('target', self.target)]:
            for record in records:
                if record.id not in self.used | self.explained:
                    self.issue('unmatched_' + side, [record])
        totals = {}
        for currency in sorted({r.currency for r in self.source + self.target}):
            a = sum((r.amount for r in self.source if r.currency == currency), ZERO)
            b = sum((r.amount for r in self.target if r.currency == currency), ZERO)
            totals[currency] = {'source': str(a), 'target': str(b), 'difference': str(a-b)}
        return {'matches': self.matches, 'exceptions': self.exceptions, 'total_records': len(self.source) + len(self.target),
            'matched_records': len(self.used), 'unmatched_records': len(self.source) + len(self.target) - len(self.used),
            'totals_by_currency': totals, 'workflow': self.kind, 'rule_version': VERSION}


def invoice_workflow(source, target, support, rules, kind):
    result = Outcome(source, target, kind)
    invoices = defaultdict(list)
    for record in source:
        if not reference(record) or not record.counterparty:
            result.issue('missing_invoice_identity', [record])
        else:
            invoices[(reference(record), record.counterparty)].append(record)
    consumed_targets = set()
    for (invoice_id, party), documents in invoices.items():
        payments = [r for r in target if reference(r) == invoice_id and r.counterparty == party]
        wrong_party = [r for r in target if reference(r) == invoice_id and r.counterparty != party]
        if wrong_party and not payments:
            independently_allocatable=any((invoice_id,r.counterparty) in invoices for r in wrong_party)
            result.issue('counterparty_mismatch', documents if independently_allocatable else documents + wrong_party,
                evidence={'candidate_ids':[r.id for r in wrong_party]})
            if not independently_allocatable:
                consumed_targets.update(r.id for r in wrong_party)
            continue
        main = [r for r in documents if field(r, 'document_type', 'INVOICE') not in ('CREDIT_NOTE', 'CREDIT')]
        credits = [r for r in documents if r not in main]
        if len(main) != 1:
            result.issue('duplicate_invoice' if len(main) > 1 else 'unmatched_credit_note', documents + payments)
            consumed_targets.update(r.id for r in payments)
            continue
        invoice = main[0]
        if len({r.currency for r in documents + payments}) > 1:
            result.issue('currency_mismatch', documents + payments)
            consumed_targets.update(r.id for r in payments)
            continue
        due = abs(invoice.amount) - sum((abs(r.amount) for r in credits), ZERO)
        paid = sum((-abs(r.amount) if field(r, 'document_type') == 'REFUND' else abs(r.amount) for r in payments), ZERO)
        delta = due - paid
        evidence = {'invoice_id': invoice_id, 'counterparty': party, 'invoice_total': str(abs(invoice.amount)),
            'credit_total': str(sum((abs(r.amount) for r in credits), ZERO)), 'amount_due': str(due), 'allocated_payment': str(paid), 'difference': str(delta)}
        if due < 0:
            result.issue('excess_credit_note', documents + payments, -due, evidence)
        elif kind == 'ap':
            po_id = field(invoice, 'po_id')
            orders = [r for r in support if (field(r, 'po_id') or r.reference) == po_id and r.counterparty == party]
            if not po_id or len(orders) != 1:
                result.issue('missing_purchase_order' if not orders else 'ambiguous_purchase_order', documents + payments, due, evidence)
            elif orders[0].currency != invoice.currency:
                result.issue('currency_mismatch', documents + payments + orders, due, evidence)
            elif abs(abs(orders[0].amount) - abs(invoice.amount)) > rules.amount_tolerance:
                result.issue('purchase_order_amount_mismatch', documents + payments + orders,
                    abs(orders[0].amount) - abs(invoice.amount), evidence)
            elif not payments or abs(delta) > rules.amount_tolerance:
                result.issue('missing_payment' if not payments else 'partial_payment' if 0 < paid < due else 'underpayment' if delta > 0 else 'overpayment', documents + payments, delta, evidence)
            else:
                result.match(documents, payments, evidence | {'purchase_order_ids': [orders[0].id]})
        elif not payments and due != 0:
            result.issue('missing_receipt', documents, due, evidence)
        elif abs(delta) > rules.amount_tolerance:
            result.issue('short_payment' if delta > 0 else 'overpayment', documents + payments, delta, evidence)
        else:
            result.match(documents, payments, evidence)
        consumed_targets.update(r.id for r in payments)
    for record in target:
        if record.id not in consumed_targets:
            result.issue('unallocated_receipt' if kind == 'ar' else 'missing_invoice', [record])
    return result.finish()


def gateway_workflow(source, target, rules):
    result = Outcome(source, target, 'gateway')
    batches = defaultdict(list)
    for record in source:
        batch = field(record, 'batch_id')
        if batch:
            batches[batch].append(record)
        else:
            result.issue('missing_batch_id', [record])
    for batch, records in batches.items():
        settlements = [r for r in target if (field(r, 'batch_id') or r.reference) == batch]
        evidence = {'batch_id': batch}
        if len({r.currency for r in records + settlements}) > 1:
            result.issue('currency_mismatch', records + settlements, evidence=evidence)
            continue
        supported = {'PAYMENT', 'REFUND', 'CHARGEBACK', 'FEE'}
        if any(field(r, 'document_type') not in supported for r in records):
            result.issue('unknown_gateway_transaction_type', records + settlements, evidence=evidence)
            continue
        gross = sum((abs(r.amount) for r in records if field(r, 'document_type') == 'PAYMENT'), ZERO)
        deductions = {kind: sum((abs(r.amount) for r in records if field(r, 'document_type') == kind), ZERO) for kind in ('REFUND', 'CHARGEBACK', 'FEE')}
        expected = gross - sum(deductions.values(), ZERO)
        deposited = sum((r.amount for r in settlements), ZERO)
        evidence |= {'gross': str(gross), **{k.lower(): str(v) for k,v in deductions.items()}, 'expected_net': str(expected), 'deposited': str(deposited), 'difference': str(expected-deposited)}
        # An explicitly supplied expected fee is independently compared to actual fee rows.
        expected_fees = [business(r).get('expected_fee') for r in records if business(r).get('expected_fee') not in (None,'')]
        if expected_fees and abs(sum((Decimal(str(v)) for v in expected_fees), ZERO) - deductions['FEE']) > rules.amount_tolerance:
            result.issue('fee_discrepancy', records + settlements, deductions['FEE'] - sum((Decimal(str(v)) for v in expected_fees), ZERO), evidence)
        elif not settlements:
            result.issue('missing_settlement', records, expected, evidence)
        elif abs(expected-deposited) > rules.amount_tolerance:
            result.issue('settlement_discrepancy', records + settlements, expected-deposited, evidence)
        elif max(abs((date.fromisoformat(a.date)-date.fromisoformat(b.date)).days) for a in records for b in settlements) > rules.date_days:
            result.issue('settlement_delay', records + settlements, expected, evidence)
        else:
            result.match(records, settlements, evidence)
    return result.finish()


def intercompany_workflow(source, target, rules):
    result = Outcome(source, target, 'intercompany')
    visited = set()
    for record in source:
        peers = [r for r in target if r.reference and r.reference == record.reference]
        related = [s for s in source if s.reference == record.reference]
        if len(peers) != 1 or len(related) != 1 or not record.reference:
            result.issue('ambiguous_reciprocal' if peers else 'missing_intercompany_posting', [record] + peers)
            visited.update(r.id for r in peers)
            continue
        peer = peers[0]
        visited.add(peer.id)
        company, counterparty = field(record,'entity_id'), field(record,'counterparty_entity')
        if not company or not counterparty or company == counterparty or company != field(peer,'counterparty_entity') or counterparty != field(peer,'entity_id'):
            result.issue('counterparty_mismatch', [record,peer])
        elif record.currency != peer.currency:
            result.issue('currency_mismatch', [record,peer])
        elif abs(record.amount + peer.amount) > rules.amount_tolerance:
            result.issue('unbalanced_reciprocal', [record,peer], record.amount + peer.amount,
                {'source_amount':str(record.amount),'reciprocal_amount':str(peer.amount)})
        elif abs((date.fromisoformat(record.date)-date.fromisoformat(peer.date)).days) > rules.date_days:
            result.issue('timing_difference',[record,peer])
        else:
            result.match([record],[peer],{'entity_id':company,'counterparty_entity':counterparty,'reciprocal_sum':str(record.amount+peer.amount)})
    for record in target:
        if record.id not in visited:
            result.issue('missing_intercompany_posting',[record])
    return result.finish()


def gl_workflow(source, target, rules):
    result = Outcome(source, target, 'gl')
    invalid = set()
    journals = defaultdict(list)
    for record in source + target:
        journal = field(record,'journal_id')
        if journal:
            journals[(getattr(record,'dataset_id',''),journal,record.currency)].append(record)
    for key, records in journals.items():
        if sum((r.amount for r in records),ZERO) != 0:
            result.issue('unbalanced_journal', records, sum((r.amount for r in records),ZERO), {'journal_id':key[1]})
            invalid.update(r.id for r in records)
    groups = defaultdict(lambda:[[],[]])
    mapping = {k.upper():v.upper() for k,v in rules.account_mapping.items()}
    for side, records in enumerate((source,target)):
        fingerprints = defaultdict(list)
        for record in records:
            fingerprints[(record.account,record.currency,record.date,record.reference,record.amount)].append(record)
        for fingerprint, duplicates in fingerprints.items():
            if len(duplicates)>1 and fingerprint[3]:
                result.issue('duplicate_posting',duplicates)
                invalid.update(r.id for r in duplicates)
        for record in records:
            if record.id not in invalid:
                account = mapping.get(record.account, record.account) if side==0 else record.account
                groups[(account,record.currency,field(record,'accounting_period') or record.date[:7])][side].append(record)
    for (account,currency,period),(left,right) in groups.items():
        delta=sum((r.amount for r in left),ZERO)-sum((r.amount for r in right),ZERO)
        evidence={'mapped_account':account,'currency':currency,'accounting_period':period,'balance_difference':str(delta)}
        if not left or not right:
            result.issue('missing_gl_account' if not right else 'missing_subledger_account',left+right,delta,evidence)
        elif abs(delta)>rules.amount_tolerance:
            result.issue('balance_difference',left+right,delta,evidence)
        else:
            result.match(left,right,evidence)
    return result.finish()


def _reconcile_workflow(source, target, rules, kind='bank', support=None):
    if kind in ('ap','ar'):
        return invoice_workflow(source,target,support or [],rules,kind)
    if kind=='gateway':
        return gateway_workflow(source,target,rules)
    if kind=='intercompany':
        return intercompany_workflow(source,target,rules)
    if kind=='gl':
        return gl_workflow(source,target,rules)
    if kind!='bank':
        raise ValueError('Unsupported accounting workflow')
    return reconcile(source,target,rules)


def reconcile_workflow(source,target,rules,kind='bank',support=None):
    from .quality_rules import duplicate_groups,unusual_values
    issues=[]
    excluded=set()
    for side,records in (('source',source),('target',target)):
        # AP invoice identities are handled by the three-way invoice workflow.
        candidates=records if kind not in ('ap','ar') or side=='target' else []
        for group in duplicate_groups(candidates):
            excluded.update(r.id for r in group)
            issues.append({'category':'duplicate_transaction','severity':'high','amount':str(abs(group[0].amount)),
                'currency':group[0].currency,'evidence':{'transaction_ids':[r.id for r in group],'side':side,
                    'rule_version':'duplicate-v1','reason':'Same financial fingerprint across different record identifiers; manual review required'}})
    result=_reconcile_workflow([r for r in source if r.id not in excluded],[r for r in target if r.id not in excluded],rules,kind,support)
    if issues:
        result['exceptions']=issues+result['exceptions']
        result['total_records']=len(source)+len(target)
        result['unmatched_records']=result['total_records']-result['matched_records']
        # Restore complete source totals, including held-for-review duplicate candidates.
        for currency in {r.currency for r in source+target}:
            a=sum((r.amount for r in source if r.currency==currency),ZERO)
            b=sum((r.amount for r in target if r.currency==currency),ZERO)
            result['totals_by_currency'][currency]={'source':str(a),'target':str(b),'difference':str(a-b)}
    explained={tid for issue in result['exceptions'] for tid in issue['evidence']['transaction_ids']}
    for record,threshold in unusual_values(source)+unusual_values(target):
        if record.id not in explained:
            result['exceptions'].append({'category':'unusual_transaction_pattern','severity':'medium','amount':str(abs(record.amount)),
                'currency':record.currency,'evidence':{'transaction_ids':[record.id],'rule_version':'iqr-v1','threshold':str(threshold),
                    'note':'Unusual amount, not proof of fraud or financial mismatch'}})
    return result
