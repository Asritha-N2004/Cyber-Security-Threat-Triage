"""Reproducible matching baseline and injected-fault controller experiment.

Run from repository root: python evaluation/run.py
No ground-truth labels are passed into the engine or provider.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.synthetic import generate
from app.ingestion import normalize
from app.schemas import Rules
from app.reconciliation_engine import reconcile
from app.orchestration import investigate
from app.providers import MockProvider


def run():
    bank, ledger = generate(seed=42, count=100)
    source = [SimpleNamespace(id=r['transaction_id'], **normalize(r,{})) for r in bank]
    target = [SimpleNamespace(id=r['transaction_id'], **normalize(r,{})) for r in ledger]
    # Separately constructed generator ground truth; excludes injected discrepancies.
    expected = {(f'B{i:04}',f'L{i:04}') for i in range(100) if i not in (1,2,3,4,5)}
    results = {}
    for name, rules in [('rules',Rules(fuzzy_enabled=False)),('rules_plus_fuzzy',Rules())]:
        outcome = reconcile(source,target,rules)
        predicted = {(m['source_ids'][0],m['target_ids'][0]) for m in outcome['matches'] if len(m['source_ids'])==len(m['target_ids'])==1}
        tp = len(predicted & expected)
        results[name] = {'precision':tp/len(predicted) if predicted else 0,'recall':tp/len(expected),
            'false_match_count':len(predicted-expected),'unmatched_records':outcome['unmatched_records'],
            'scope':'one-to-one synthetic ground truth; split settlement excluded from precision/recall'}
    class InjectedFault(MockProvider):
        def propose(self,context,feedback):
            p=super().propose(context,feedback)
            if not feedback:
                p.lines.pop()
            return p
    context={'supported_bank_fee':True,'amount':'25.00','currency':'USD','transaction_ids':['FEE'],'category':'unmatched_source','high_value':False}
    fault_results={}
    for limit in (1,3):
        state,_=investigate(context,InjectedFault(),limit)
        fault_results[str(limit)]={'attempts':state['iteration'],'validation_passed':state['validation']['passed']}
    results['injected_fault_experiment']={'label':'Artificial unbalanced first proposal; controller test, not evidence of LLM improvement','by_iteration_limit':fault_results}
    results['unmeasured']=['Single-agent LLM vs multi-agent LLM arms','Real-world resolution accuracy','Token usage and financial cost','Human acceptance','Latency benchmark','Production calibration']
    print(json.dumps(results,indent=2))
    return results


if __name__=='__main__':
    run()
