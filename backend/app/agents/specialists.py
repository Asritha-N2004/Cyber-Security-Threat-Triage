"""Ten independent reasoning components. Evidence tools have no write authority."""
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field
from ..schemas import Correction, Validation
from ..validation import validate_correction


class AgentOutput(BaseModel):
    agent: str
    basis: Literal['deterministic','mock','llm'] = 'deterministic'
    findings: list[str]
    evidence_ids: list[str]
    facts: dict = Field(default_factory=dict)
    uncertainty: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    cause: Literal['timing_difference','data_entry_error','missing_transaction','duplicate_posting','incorrect_amount',
        'incorrect_currency','account_mapping_issue','settlement_discrepancy','bank_charge','unknown_cause']
    explanation: str
    alternative_explanations: list[str]
    evidence_ids: list[str]
    uncertainty: list[str]


class EvidenceReader:
    def __init__(self,context):
        self.context=context
        self.records={r['id']:r for r in context.get('records',[]) if r['id'] in context['transaction_ids']}

    def get(self,identifier):
        if identifier not in self.context['transaction_ids']:
            raise ValueError('Evidence retrieval outside permitted scope')
        return self.records.get(identifier)

    def all(self):
        return [self.records[k] for k in self.context['transaction_ids'] if k in self.records]


class Agent:
    name='agent'
    def output(self,context,findings,facts=None,uncertainty=None,basis='deterministic'):
        return AgentOutput(agent=self.name,basis=basis,findings=findings,evidence_ids=context['transaction_ids'],facts=facts or {},uncertainty=uncertainty or [])


class DataQualityAgent(Agent):
    name='Data quality'
    def run(self,context,state):
        records=EvidenceReader(context).all()
        missing=[r['id'] for r in records if not all(r.get(k) not in ('',None) for k in ('amount','currency','account','date'))]
        rejected=sum(report.get('rejected',0) for report in context.get('quality_reports',[]))
        return self.output(context,[f'{len(records)} scoped records retrieved; {rejected} rejected import rows remain visible'],
            {'missing_fields':missing,'rejected_import_rows':rejected,'validation_passed':not missing})


class BankStatementAgent(Agent):
    name='Bank statement analysis'
    def run(self,context,state):
        dictionary=context.get('bank_codes',{'BANK_FEE':'bank_charge'})
        interpretations=[]
        for record in EvidenceReader(context).all():
            code=str(record.get('original',{}).get('transaction_type','')).upper()
            if code in dictionary:
                interpretations.append({'record_id':record['id'],'code':code,'meaning':dictionary[code]})
        return self.output(context,[f'{len(interpretations)} codes interpreted using the tenant dictionary'],
            {'code_interpretations':interpretations,'supported_bank_fee':context['supported_bank_fee']},
            [] if interpretations else ['No configured bank code establishes a financial cause'])


class GeneralLedgerAgent(Agent):
    name='General ledger analysis'
    def run(self,context,state):
        records=EvidenceReader(context).all()
        journals=defaultdict(list)
        fingerprints=Counter((r.get('dataset_id'),r.get('reference'),r.get('account'),r.get('date'),r.get('amount')) for r in records)
        for record in records:
            journal=record.get('original',{}).get('journal_id')
            if journal:
                journals[(record.get('dataset_id'),journal,record['currency'])].append(record)
        balances={str(key):str(sum((Decimal(r['amount']) for r in values),Decimal(0))) for key,values in journals.items()}
        duplicates=sum(count-1 for key,count in fingerprints.items() if count>1 and key[1])
        return self.output(context,[f'{len(journals)} journals recalculated; {duplicates} duplicate posting candidates'],
            {'journal_balances':balances,'duplicate_candidates':duplicates,'source_integrity':'immutable'})


class TransactionMatchingAgent(Agent):
    name='Transaction matching'
    def run(self,context,state):
        evidence=context.get('matching_evidence',{})
        records=EvidenceReader(context).all()
        candidates=evidence.get('candidate_ids',[])
        candidate_records=[r for r in records if r['id'] in candidates]
        alternatives=[{'transaction_id':r['id'],'amount':r['amount'],'currency':r['currency'],'date':r['date'],'reference':r.get('reference','')} for r in candidate_records]
        return self.output(context,['Deterministic candidates reviewed; constraints cannot be overridden',
            'Manual review required for ambiguous candidates' if candidates else 'No alternative match proven by scoped records'],
            {'candidate_ids':candidates,'alternative_candidates':alternatives,'currency_agreement':len({r['currency'] for r in records})<=1,'match_authorized':False,'evidence':evidence})


class ExceptionClassificationAgent(Agent):
    name='Exception classification'
    def run(self,context,state):
        category=context['category']
        severity='high' if context['high_value'] or category in ('currency_mismatch','account_mismatch','duplicate_posting','duplicate_invoice','unbalanced_journal') else 'medium'
        return self.output(context,[f'Discrepancy: {category}; severity: {severity}'],
            {'category':category,'severity':severity,'financial_impact':context['amount'],'currency':context['currency']})


class RootCauseAgent(Agent):
    name='Root cause analysis'
    def __init__(self,provider=None):
        self.provider=provider
    def run(self,context,state):
        if self.provider and self.provider.name!='mock' and hasattr(self.provider,'diagnose'):
            safe={k:v for k,v in context.items() if k not in ('records','quality_reports')}
            diagnosis=Diagnosis.model_validate(self.provider.diagnose(safe,state.get('agents',[])))
            if set(diagnosis.evidence_ids)-set(context['transaction_ids']):
                raise ValueError('Diagnosis referenced evidence outside scope')
            return self.output(context,[diagnosis.explanation],{'diagnosis':diagnosis.model_dump(mode='json'),'verified':False},diagnosis.uncertainty,'llm')
        known={'timing_difference':'timing_difference','settlement_delay':'timing_difference','duplicate_posting':'duplicate_posting',
            'duplicate_invoice':'duplicate_posting','account_mismatch':'account_mapping_issue','settlement_discrepancy':'settlement_discrepancy'}
        cause='bank_charge' if context['supported_bank_fee'] else known.get(context['category'],'unknown_cause')
        diagnosis=Diagnosis(cause=cause,explanation='Explicit code identifies a bank charge' if context['supported_bank_fee'] else
            'Observed evidence supports a discrepancy category; source authority remains unproven',
            alternative_explanations=['Incorrect source mapping','Missing supporting record'] if cause!='bank_charge' else ['Organization-specific fee account mapping'],
            evidence_ids=context['transaction_ids'],uncertainty=[] if cause=='bank_charge' else ['Underlying cause requires authoritative documents or human investigation'])
        return self.output(context,[diagnosis.explanation],{'diagnosis':diagnosis.model_dump(mode='json')},diagnosis.uncertainty)


class CorrectionRecommendationAgent(Agent):
    name='Correction recommendation'
    def __init__(self,provider):
        self.provider=provider
    def run(self,context,state):
        safe={k:v for k,v in context.items() if k not in ('records','quality_reports')}
        safe['evidence_records']=[{key:record[key] for key in ('id','amount','currency','account','date','reference') if key in record} for record in EvidenceReader(context).all()]
        safe['specialist_findings']=[a for a in state.get('agents',[]) if a['agent'] not in ('Correction recommendation','Independent validation','Self-correction controller','Decision explanation')]
        proposal=Correction.model_validate(self.provider.propose(safe,state.get('validation',{}).get('findings',[])))
        return self.output(context,[proposal.rationale],{'proposal':proposal.model_dump(mode='json'),'provider_usage':getattr(self.provider,'usage',None)},proposal.uncertainty,
            'mock' if self.provider.name=='mock' else 'llm')


class IndependentValidationAgent(Agent):
    name='Independent validation'
    def run(self,context,state):
        validation=validate_correction(Correction.model_validate(state['proposal']),context)
        source_ids=[r['id'] for r in EvidenceReader(context).all()]
        findings=validation.findings.copy()
        from ..ingestion import normalize
        for record in EvidenceReader(context).all():
            if record.get('original'):
                try:
                    metadata=record.get('normalization',{})
                    independently=normalize(record['original'],metadata.get('mapping',{}),metadata.get('source_timezone','UTC'))
                    if Decimal(str(record['amount']))!=independently['amount'] or any(record.get(key)!=independently[key] for key in ('currency','account','date','reference')):
                        findings.append('Canonical record does not agree with independently normalized immutable source')
                except (ValueError,TypeError,KeyError):
                    findings.append('Source record cannot be independently normalized')
        if context.get('records') and set(source_ids)!=set(context['transaction_ids']):
            findings.append('Not all referenced evidence was retrieved')
        validation=Validation(passed=not findings,findings=findings)
        proposal=Correction.model_validate(state['proposal'])
        before=Decimal(context['amount'])
        cash_credit=sum((line.credit-line.debit for line in proposal.lines if line.account==proposal.cash_account),Decimal(0))
        return self.output(context,findings or ['Accounting, evidence, policy and source-integrity checks passed'],
            {'validation':validation.model_dump(),'attributable_discrepancy_before':str(before),
                'simulated_discrepancy_after':str(before-cash_credit),'exception_resolved':False})


class SelfCorrectionControllerAgent(Agent):
    name='Self-correction controller'
    def run(self,context,state):
        passed=state['validation']['passed']
        retry=not passed and state['iteration']<state['max_iterations']
        return self.output(context,[f"Attempt {state['iteration']} of {state['max_iterations']}: {'reassess' if retry else 'human review' if passed else 'escalate'}"],
            {'retry':retry,'decision':'revise' if retry else 'review' if passed else 'escalate','resolved':False})


class DecisionExplanationAgent(Agent):
    name='Decision explanation'
    def run(self,context,state):
        passed=state.get('validation',{}).get('passed',False)
        return self.output(context,['Source records remain unchanged',
            'Draft passed checks; approval remains required' if passed else 'Unresolved validation requires escalation',
            'An investigation or simulated journal never proves external resolution'],
            {'validation_passed':passed,'proposal_attempts':state['iteration'],'exception_resolved':False},state.get('proposal',{}).get('uncertainty',[]))


AGENTS=[DataQualityAgent,BankStatementAgent,GeneralLedgerAgent,TransactionMatchingAgent,ExceptionClassificationAgent,
    RootCauseAgent,CorrectionRecommendationAgent,IndependentValidationAgent,SelfCorrectionControllerAgent,DecisionExplanationAgent]
