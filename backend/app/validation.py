from decimal import Decimal
from .schemas import Correction, Validation
from .policies import period_findings


def validate_correction(proposal: Correction, context: dict) -> Validation:
    findings = []
    if not proposal.evidence_ids or set(proposal.evidence_ids) != set(context['transaction_ids']):
        findings.append('Evidence must exactly reference the source records')
    if proposal.currency != context['currency']:
        findings.append('Currency must agree with source evidence')
    if proposal.target_record is not None and proposal.target_record not in context['transaction_ids']:
        findings.append('Target record is outside the approved evidence scope')
    if proposal.action == 'manual_review':
        if proposal.lines or proposal.financial_impact != 0:
            findings.append('Manual review cannot carry a financial posting')
    else:
        findings.extend(period_findings(proposal.posting_date,context))
        if proposal.policy_version != context.get('policy_version',1):
            findings.append('Proposal uses a stale accounting policy; reassessment and fresh approval required')
        if not context['supported_bank_fee']:
            findings.append('No authorized BANK_FEE evidence supports a journal draft')
        debit = sum((line.debit for line in proposal.lines), Decimal(0))
        credit = sum((line.credit for line in proposal.lines), Decimal(0))
        if debit != credit or debit <= 0:
            findings.append('Journal debits and credits must balance and be positive')
        if any((line.debit > 0 and line.credit > 0) or (line.debit == line.credit == 0) for line in proposal.lines):
            findings.append('Each journal line requires exactly one debit or credit')
        expected = Decimal(context['amount'])
        if proposal.financial_impact != expected or debit != expected:
            findings.append('Financial impact must equal the evidenced discrepancy')
        actual = sorted((line.account, str(line.debit.normalize()), str(line.credit.normalize())) for line in proposal.lines)
        mapping = context.get('account_mapping', {'fees':'fees','cash':'cash'})
        if proposal.cash_account != mapping.get('cash','cash'):
            findings.append('Cash account must agree with the approved tenant mapping')
        required = sorted([(mapping.get('fees','fees'), str(expected.normalize()), '0'), (mapping.get('cash','cash'), '0', str(expected.normalize()))])
        if actual != required:
            findings.append('Journal must debit fees and credit cash by the evidenced bank charge')
        for line in proposal.lines:
            from .ingestion import CURRENCY_PRECISION
            quantum=Decimal(1).scaleb(-CURRENCY_PRECISION.get(proposal.currency,2))
            if any(value!=value.quantize(quantum) for value in (line.debit,line.credit)):
                findings.append('Journal precision is incompatible with its currency')
            if 'accounts' in context:
                account=context['accounts'].get(line.account)
                if not account or not account['active'] or account['currency'] not in ('*',proposal.currency):
                    findings.append('Journal references an invalid, inactive or incompatible tenant account')
        approval = 'dual' if context['high_value'] else 'single'
        if proposal.required_approval != approval:
            findings.append(f'Policy requires {approval} approval')
    return Validation(passed=not findings, findings=findings)
