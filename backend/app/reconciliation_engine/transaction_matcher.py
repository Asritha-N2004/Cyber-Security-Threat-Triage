from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from itertools import combinations
from app.schemas import Rules

RULE_VERSION = 'conservative-v1'


def evidence(left, right):
    return {
        'amount_difference': str(left.amount - right.amount),
        'date_days': abs((date.fromisoformat(left.date) - date.fromisoformat(right.date)).days),
        'reference_agreement': bool(left.reference) and left.reference == right.reference,
        'description_similarity': SequenceMatcher(None, left.description, right.description).ratio() if left.description and right.description else 0,
        'counterparty_agreement': bool(left.counterparty) and left.counterparty == right.counterparty,
        'account_agreement': left.account == right.account,
        'currency_agreement': left.currency == right.currency,
        'rule_version': RULE_VERSION,
    }


def compatible(left, right, rules):
    return left.currency == right.currency and left.account == right.account and (
        (left.amount >= 0) == (right.amount >= 0)) and abs((date.fromisoformat(left.date) - date.fromisoformat(right.date)).days) <= rules.date_days


def reconcile(source, target, rules: Rules):
    used_s, used_t, matches = set(), set(), []
    # Accept only mutual unique candidates. Scores are evidence, never probabilities.
    def accept_candidates(candidates, kind):
        for left, right, ev in candidates:
            if sum(x.id == left.id for x, _, _ in candidates) != 1 or sum(y.id == right.id for _, y, _ in candidates) != 1:
                continue
            if left.id not in used_s and right.id not in used_t:
                used_s.add(left.id)
                used_t.add(right.id)
                matches.append({'kind': kind, 'source_ids': [left.id], 'target_ids': [right.id], **ev})

    for kind in ('exact', 'fuzzy'):
        if kind == 'fuzzy' and not rules.fuzzy_enabled:
            continue
        candidates = []
        for left in source:
            for right in target:
                if left.id in used_s or right.id in used_t or not compatible(left, right, rules):
                    continue
                ev = evidence(left, right)
                if abs(left.amount - right.amount) > rules.amount_tolerance:
                    continue
                sufficient = ev['reference_agreement'] if kind == 'exact' else ev['description_similarity'] >= rules.fuzzy_threshold and ev['counterparty_agreement']
                if sufficient:
                    candidates.append((left, right, ev))
        accept_candidates(candidates, kind)

    # Bounded subset search; common nonempty batch reference is mandatory.
    groups = []
    for reverse in (False, True):
        single, multiple = (target, source) if reverse else (source, target)
        single_used, multi_used = (used_t, used_s) if reverse else (used_s, used_t)
        for one in single:
            if one.id in single_used or not one.reference:
                continue
            pool = [t for t in multiple if t.id not in multi_used and t.reference == one.reference and compatible(one, t, rules)]
            if len(pool) > 16:  # Explicit operational search bound; leftovers remain visible.
                continue
            for size in range(2, min(len(pool), rules.max_group) + 1):
                for group in combinations(pool, size):
                    if abs(one.amount - sum((t.amount for t in group), Decimal(0))) <= rules.amount_tolerance:
                        sids, tids = ([t.id for t in group], [one.id]) if reverse else ([one.id], [t.id for t in group])
                        groups.append({'kind': 'many_to_one' if reverse else 'one_to_many',
                            'source_ids': sids, 'target_ids': tids, 'reference': one.reference,
                            'amount_difference': str(one.amount - sum((t.amount for t in group), Decimal(0))),
                            'rule_version': RULE_VERSION})
    for group in groups:
        identifiers = set(group['source_ids'] + group['target_ids'])
        if any(other is not group and identifiers.intersection(other['source_ids'] + other['target_ids']) for other in groups):
            continue
        if used_s.intersection(group['source_ids']) or used_t.intersection(group['target_ids']):
            continue
        matches.append(group)
        used_s.update(group['source_ids'])
        used_t.update(group['target_ids'])

    remaining_s = [t for t in source if t.id not in used_s]
    remaining_t = [t for t in target if t.id not in used_t]
    exceptions, paired = [], set()
    for left in remaining_s:
        peers = [t for t in remaining_t if t.id not in paired and left.reference and left.reference == t.reference]
        category = 'unmatched_source'
        ids = [left.id]
        if len(peers) == 1 and sum(s.reference == left.reference for s in remaining_s) == 1:
            right = peers[0]
            paired.add(right.id)
            ids.append(right.id)
            ev = evidence(left, right)
            if not ev['currency_agreement']:
                category = 'currency_mismatch'
            elif not ev['account_agreement']:
                category = 'account_mismatch'
            elif abs(left.amount - right.amount) > rules.amount_tolerance:
                category = 'amount_mismatch'
            elif ev['date_days'] > rules.date_days:
                category = 'timing_difference'
            else:
                category = 'ambiguous_match'
        else:
            ev = {'candidate_ids': [t.id for t in peers]}
            if len(peers) > 1:
                category = 'ambiguous_match'
        exceptions.append({'category': category, 'amount': str(abs(left.amount)), 'currency': left.currency,
            'severity': 'high' if category in ('currency_mismatch', 'account_mismatch') or abs(left.amount) >= 10000 else 'medium',
            'evidence': {'transaction_ids': ids, 'side': 'source', 'rule_version': RULE_VERSION, **ev}})
    for right in remaining_t:
        if right.id not in paired:
            exceptions.append({'category': 'unmatched_target', 'amount': str(abs(right.amount)), 'currency': right.currency,
                'severity': 'medium', 'evidence': {'transaction_ids': [right.id], 'side': 'target', 'rule_version': RULE_VERSION}})
    assert len(used_s) == sum(len(m['source_ids']) for m in matches)
    assert len(used_t) == sum(len(m['target_ids']) for m in matches)
    totals = {}
    for currency in sorted({t.currency for t in source + target}):
        a = sum((t.amount for t in source if t.currency == currency), Decimal(0))
        b = sum((t.amount for t in target if t.currency == currency), Decimal(0))
        totals[currency] = {'source': str(a), 'target': str(b), 'difference': str(a-b)}
    return {'matches': matches, 'exceptions': exceptions, 'total_records': len(source) + len(target),
        'matched_records': len(used_s) + len(used_t), 'unmatched_records': len(remaining_s) + len(remaining_t),
        'totals_by_currency': totals, 'rule_version': RULE_VERSION}
