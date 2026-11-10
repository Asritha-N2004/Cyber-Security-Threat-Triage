from datetime import date
import os
from decimal import Decimal
from sqlalchemy import select
from .models_extended import AccountingPolicy, FinancialAccount

DEFAULTS = {'closed_through': None, 'dual_approval_threshold': '10000', 'account_mapping': {'cash': 'cash', 'fees': 'fees'},
    'bank_codes': {'BANK_FEE': 'bank_charge', 'INTEREST': 'interest_credit', 'SETTLEMENT': 'settlement'},
    'retention_days': 2555, 'source_timezone': 'UTC'}


def ensure_policy(db, org_id):
    policy = db.get(AccountingPolicy, org_id)
    if policy is None:
        policy = AccountingPolicy(org_id=org_id, version=1, settings=DEFAULTS|{'dual_approval_threshold':os.getenv('DUAL_APPROVAL_THRESHOLD','10000')})
        db.add(policy)
        for code in ('cash', 'fees', 'suspense', 'receivable', 'payable'):
            db.add(FinancialAccount(org_id=org_id, code=code, name=code.title(), currency='*', active=True))
        db.flush()
    return policy


def policy_context(db, org_id):
    policy = ensure_policy(db, org_id)
    accounts = list(db.scalars(select(FinancialAccount).where(FinancialAccount.org_id == org_id)))
    return {'policy_version': policy.version, 'closed_through': policy.settings.get('closed_through'),
        'account_mapping': policy.settings.get('account_mapping', {}),
        'accounts': {a.code: {'currency': a.currency, 'active': a.active} for a in accounts},
        'bank_codes': policy.settings.get('bank_codes', {}), 'dual_approval_threshold': policy.settings.get('dual_approval_threshold','10000')}


def period_findings(posting_date, context):
    if not posting_date:
        return ['Posting date is required']
    try:
        posted = date.fromisoformat(str(posting_date))
    except ValueError:
        return ['Posting date must be an ISO date']
    closed = context.get('closed_through')
    return ['Posting date is in a closed accounting period'] if closed and posted <= date.fromisoformat(closed) else []
