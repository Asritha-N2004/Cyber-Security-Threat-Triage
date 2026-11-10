import random


def generate(seed=42, count=30):
    randomizer = random.Random(seed)
    bank, ledger = [], []
    for index in range(count):
        row = {'transaction_id': f'B{index:04}', 'date': '2026-01-15', 'currency': 'USD',
            'account': 'cash', 'reference': f'INV-{index:04}', 'description': f'Synthetic invoice payment {index}',
            'counterparty': f'Synthetic customer {index}', 'amount': f'{randomizer.randint(100, 999)}.00'}
        bank.append(row)
        ledger.append(row | {'transaction_id': f'L{index:04}'})
    bank += [
        {'transaction_id': 'FEE', 'date': '2026-01-15', 'currency': 'USD', 'account': 'cash', 'reference': 'FEE-JAN', 'description': 'Synthetic bank service charge', 'transaction_type': 'BANK_FEE', 'amount': '-25.00'},
        {'transaction_id': 'SETTLE', 'date': '2026-01-15', 'currency': 'USD', 'account': 'cash', 'reference': 'BATCH-1', 'description': 'Synthetic settlement', 'amount': '300.00'},
        {'transaction_id': 'MISSING', 'date': '2026-01-15', 'currency': 'USD', 'account': 'cash', 'reference': 'UNKNOWN', 'description': 'Synthetic insufficient evidence', 'amount': '88.00'}]
    ledger += [{'transaction_id': f'SPLIT-{i}', 'date': '2026-01-15', 'currency': 'USD', 'account': 'cash', 'reference': 'BATCH-1', 'description': 'Synthetic settlement component', 'amount': amount} for i, amount in enumerate(['100.00', '200.00'])]
    if count >= 6:
        ledger[1]['amount'] = str(int(bank[1]['amount'].split('.')[0]) + 10) + '.00'
        ledger[2]['currency'] = 'EUR'
        ledger[3]['date'] = '2026-02-15'
        ledger[4]['account'] = 'other'
        ledger.pop(5)
    return bank, ledger
