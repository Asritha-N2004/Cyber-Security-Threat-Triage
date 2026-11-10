from app.providers import MockProvider
from app.orchestration import investigate
from app.schemas import Correction
from app.validation import validate_correction

CONTEXT = {'supported_bank_fee': True, 'amount': '25.00', 'transaction_ids': ['bank-fee'],
    'currency': 'USD', 'category': 'unmatched_source', 'high_value': False}


def test_independent_validator_rejects_unbalanced_and_unsupported():
    proposal = MockProvider().propose(CONTEXT, [])
    assert validate_correction(proposal, CONTEXT).passed
    proposal.lines.pop()
    assert not validate_correction(proposal, CONTEXT).passed
    assert not validate_correction(MockProvider().propose(CONTEXT, []), CONTEXT | {'supported_bank_fee': False}).passed


def test_targeted_self_correction():
    class FaultyOnce(MockProvider):
        def propose(self, context, feedback):
            proposal = super().propose(context, feedback)
            if not feedback:
                proposal.lines.pop()
            return proposal
    state, analysis = investigate(CONTEXT, FaultyOnce())
    assert len(state['history']) == 2
    assert not state['history'][0]['validation']['passed']
    assert state['history'][1]['validation']['passed']


def test_iteration_limit_and_failure():
    class AlwaysBad(MockProvider):
        def propose(self, context, feedback):
            proposal = super().propose(context, feedback)
            proposal.lines.pop()
            return proposal
    state, _ = investigate(CONTEXT, AlwaysBad())
    assert state['iteration'] == 3 and not state['validation']['passed']
    class Failed(MockProvider):
        def propose(self, context, feedback):
            raise TimeoutError()
    state, _ = investigate(CONTEXT, Failed())
    assert state['failure'] and state['iteration'] == 1


def test_currency_specific_journal_precision():
    context=CONTEXT|{'currency':'KWD','amount':'25.123'}
    proposal=MockProvider().propose(context,[])
    assert validate_correction(proposal,context).passed
    assert not validate_correction(proposal.model_copy(update={'currency':'JPY'}),context|{'currency':'JPY'}).passed
