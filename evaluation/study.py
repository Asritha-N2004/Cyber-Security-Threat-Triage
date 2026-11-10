"""Six reproducible ablation arms. Mock results are never labeled LLM evidence."""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.synthetic import generate
from app.ingestion import normalize
from app.providers import get_provider
from app.reconciliation_engine import reconcile
from app.schemas import Rules
from app.orchestration import investigate
from app.validation import validate_correction

ARMS=('A_rules','B_fuzzy','C_single_agent','D_multi_agent','E_independent_validation','F_self_correction')


def study(seeds=(41,42,43),count=100,provider_name='mock'):
    if provider_name not in ('mock','openai'):
        raise ValueError('Provider must be mock or openai')
    os.environ['LLM_PROVIDER']=provider_name
    results={arm:[] for arm in ARMS}
    for seed in seeds:
        bank,ledger=generate(seed,count)
        # Reference corruption creates a separately labeled fuzzy-recoverable pair.
        if count>8:
            ledger[6]['reference']='PROVIDER-REF-6'
        source=[SimpleNamespace(id=r['transaction_id'],original=r,normalization={},**normalize(r,{})) for r in bank]
        target=[SimpleNamespace(id=r['transaction_id'],original=r,normalization={},**normalize(r,{})) for r in ledger]
        truth={(f'B{i:04}',f'L{i:04}') for i in range(count) if i not in (1,2,3,4,5)}
        for arm in ARMS:
            started=time.perf_counter()
            outcome=reconcile(source,target,Rules(fuzzy_enabled=arm!='A_rules'))
            predicted={(m['source_ids'][0],m['target_ids'][0]) for m in outcome['matches'] if len(m['source_ids'])==len(m['target_ids'])==1}
            tp=len(predicted&truth)
            attempts,passed,escalations,proposals,tokens=0,0,0,0,0
            classification_correct,root_correct,root_unknown=0,0,0
            truth_categories={'B0001':'amount_mismatch','B0002':'currency_mismatch','B0003':'timing_difference','B0004':'account_mismatch',
                'B0005':'unmatched_source','B0006':'reference_mismatch','L0006':'reference_mismatch','FEE':'unmatched_source','MISSING':'unmatched_source'}
            truth_causes={'B0001':'incorrect_amount','B0002':'incorrect_currency','B0003':'timing_difference','B0004':'account_mapping_issue',
                'B0005':'missing_transaction','B0006':'data_entry_error','L0006':'data_entry_error','FEE':'bank_charge','MISSING':'unknown_cause'}
            exceptions=outcome['exceptions']
            for exception in exceptions:
                label_id=next((tid for tid in exception['evidence']['transaction_ids'] if tid in truth_categories),None)
                classification_correct+=int(label_id is not None and exception['category']==truth_categories[label_id])
                if arm in ('A_rules','B_fuzzy'):
                    escalations+=1
                    continue
                ids=exception['evidence']['transaction_ids']
                scoped=[r for r in source+target if r.id in ids]
                fee=len(scoped)==1 and scoped[0].original.get('transaction_type')=='BANK_FEE' and scoped[0].amount<0
                context={'supported_bank_fee':fee,'amount':exception['amount'],'currency':exception['currency'],
                    'transaction_ids':ids,'category':exception['category'],'high_value':Decimal(exception['amount'])>=10000,
                    'records':[{'id':r.id,'amount':str(r.amount),'currency':r.currency,'account':r.account,'date':r.date,'reference':r.reference,'original':r.original} for r in scoped],
                    'matching_evidence':exception['evidence']}
                provider=get_provider()
                if arm=='C_single_agent':
                    proposal=provider.propose({k:v for k,v in context.items() if k!='records'},[])
                    attempts+=1
                    check=validate_correction(proposal,context)
                    content=proposal.model_dump(mode='json')
                    diagnosed=content['cause']
                else:
                    state,analysis=investigate(context,provider,independent_validation=arm!='D_multi_agent',self_correction=arm=='F_self_correction')
                    attempts+=state['iteration']
                    if state['failure']:
                        escalations+=1
                        continue
                    from app.schemas import Correction
                    content=state['proposal']
                    check=validate_correction(Correction.model_validate(content),context)
                    diagnosed=analysis['cause']
                root_correct+=int(label_id is not None and diagnosed==truth_causes[label_id])
                root_unknown+=int(diagnosed=='unknown_cause')
                passed+=int(check.passed)
                proposals+=int(content['action']=='draft_journal')
                escalations+=int(content['action']=='manual_review' or not check.passed)
                usage=getattr(provider,'usage',None) or {}
                tokens+=usage.get('input_tokens',0)+usage.get('output_tokens',0)
            elapsed=time.perf_counter()-started
            results[arm].append({'seed':seed,'match_precision':tp/len(predicted) if predicted else 0,'match_recall':tp/len(truth),
                'false_match_rate':len(predicted-truth)/len(predicted) if predicted else 0,'unmatched_rate':outcome['unmatched_records']/outcome['total_records'],
                'exception_count':len(exceptions),'proposal_count':proposals,'validation_pass_rate':passed/len(exceptions) if exceptions else 1,
                'human_escalation_rate':escalations/len(exceptions) if exceptions else 0,'mean_seconds_per_exception':elapsed/max(1,len(exceptions)),
                'proposal_attempts':attempts,'token_usage':tokens,'cost_per_exception':None,'real_resolution_rate':0,
                'human_acceptance_rate':None,'root_cause_accuracy':root_correct/max(1,len(exceptions)) if arm not in ('A_rules','B_fuzzy') else None,
                'root_cause_abstention_rate':root_unknown/max(1,len(exceptions)) if arm not in ('A_rules','B_fuzzy') else None,
                'exception_classification_accuracy':classification_correct/max(1,len(exceptions))})
    summary={arm:{'runs':runs,'mean_match_precision':statistics.mean(r['match_precision'] for r in runs),
        'mean_match_recall':statistics.mean(r['match_recall'] for r in runs)} for arm,runs in results.items()}
    return {'provider':provider_name,'synthetic':True,'arms':summary,'limits':[
        'Mock reasoning is a deterministic control baseline, not evidence of LLM performance.',
        'Offline validation measures proposal eligibility, never human acceptance or real resolution.',
        'Cost requires configured pricing; unavailable metrics remain null rather than fabricated.',
        'No superiority claim or production calibration is established by these small synthetic samples.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',choices=['mock','openai'],default='mock')
    parser.add_argument('--count',type=int,default=100)
    parser.add_argument('--output',default='evaluation/results.json')
    args=parser.parse_args()
    if args.count<10 or args.count>10000:
        parser.error('count must be 10–10000')
    result=study(count=args.count,provider_name=args.provider)
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'Saved six-arm {args.provider} study to {args.output}; no real-world improvement claim.')
