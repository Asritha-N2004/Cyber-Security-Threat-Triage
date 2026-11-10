from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.ingestion import normalize
from app.reconciliation_engine import reconcile
from app.schemas import Rules


def tx(id, amount='10', reference='R', **kwargs):
    return SimpleNamespace(**({'id': id, 'amount': Decimal(amount), 'reference': reference,
        'date': '2026-01-01', 'currency': 'USD', 'account': 'CASH', 'description': 'PAYMENT', 'counterparty': 'ACME'} | kwargs))


def test_exact_decimal_and_no_double_match():
    result = reconcile([tx('a', '.30')], [tx('b', '.30')], Rules())
    assert result['matched_records'] == 2
    assert Decimal(result['totals_by_currency']['USD']['difference']) == 0
    assert reconcile([tx('a')], [tx('b'), tx('c')], Rules())['matched_records'] == 0


@pytest.mark.parametrize('reverse', [False, True])
def test_groups(reverse):
    one, many = [tx('a', '30')], [tx('b', '10'), tx('c', '20')]
    result = reconcile(many if reverse else one, one if reverse else many, Rules())
    assert result['matched_records'] == 3
    assert result['matches'][0]['kind'] == ('many_to_one' if reverse else 'one_to_many')


def test_constraints_and_fuzzy():
    assert reconcile([tx('a')], [tx('b', currency='EUR')], Rules())['exceptions'][0]['category'] == 'currency_mismatch'
    assert reconcile([tx('a')], [tx('b', account='OTHER')], Rules())['matched_records'] == 0
    assert reconcile([tx('a')], [tx('b', reference='OTHER')], Rules())['matches'][0]['kind'] == 'fuzzy'
    assert reconcile([tx('a')], [tx('b', amount='10.01')], Rules(amount_tolerance='.01'))['matched_records'] == 2
    assert reconcile([tx('a')], [tx('b', date='2026-02-01')], Rules())['exceptions'][0]['category'] == 'timing_difference'


def test_normalization():
    raw = {'transaction_id': '1', 'date': '2026-01-01', 'account': 'cash', 'currency': 'USD', 'debit': '0.30'}
    assert normalize(raw, {})['amount'] == Decimal('-.30')
    for updates in ({'currency': 'XXX'}, {'debit': '-1'}, {'debit': '.001'}, {'date': '01/02/2026'}, {'amount': 'NaN'}, {'amount': '2', 'debit': '1'}):
        with pytest.raises(ValueError):
            normalize(raw | updates, {})
