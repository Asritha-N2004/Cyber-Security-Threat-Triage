"""Conservative duplicate and unusual-value detection independent of LLM reasoning."""
from collections import defaultdict
from decimal import Decimal


def duplicate_groups(records):
    groups=defaultdict(list)
    for record in records:
        original=getattr(record,'normalization',{}).get('business',getattr(record,'original',{}))
        # Explicit payment identifiers distinguish same-day installment payments.
        payment=original.get('payment_reference') or original.get('payment_id') or ''
        if record.reference:
            key=(record.account,record.currency,record.date,record.reference,record.amount,record.counterparty,
                str(original.get('document_type','')).upper(),str(payment).upper())
            groups[key].append(record)
    return [group for group in groups.values() if len(group)>1]


def unusual_values(records):
    pools=defaultdict(list)
    for record in records:
        pools[(record.account,record.currency)].append(record)
    anomalies=[]
    for pool in pools.values():
        if len(pool)<8:
            continue
        values=sorted(abs(r.amount) for r in pool)
        q1,q3=values[len(values)//4],values[(3*len(values))//4]
        threshold=q3+Decimal(3)*(q3-q1)
        for record in pool:
            if abs(record.amount)>threshold and abs(record.amount)>q3*3:
                anomalies.append((record,threshold))
    return anomalies
