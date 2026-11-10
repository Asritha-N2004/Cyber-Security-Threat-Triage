from app.orchestration import investigate
from app.providers import MockProvider
from app.agents.specialists import AGENTS, EvidenceReader
from test_controls import CONTEXT
import pytest


def test_all_ten_agents_execute_as_graph_nodes():
    checkpoints=[]
    state,analysis=investigate(CONTEXT,MockProvider(),checkpoint=lambda node,state:checkpoints.append(node))
    assert len(AGENTS)==10
    assert set(checkpoints)=={agent.__name__ for agent in AGENTS}
    assert len(state['executions'])==10
    assert len(analysis['agents'])==10
    assert state['controller']['decision']=='review' and not state['controller']['resolved']


def test_scoped_evidence_and_checkpoint_validation():
    tool=EvidenceReader(CONTEXT|{'records':[{'id':'other','amount':'999'}]})
    assert tool.all()==[]
    with pytest.raises(ValueError):
        tool.get('other')
    state,_=investigate(CONTEXT,MockProvider())
    replay,_=investigate(CONTEXT,MockProvider(),resume=state)
    assert replay['executions']==state['executions']
    with pytest.raises(ValueError):
        investigate(CONTEXT|{'transaction_ids':['wrong']},MockProvider(),resume=state)


def test_resume_partial_checkpoint_does_not_repeat_completed_agents():
    saved=[]
    def crash(node,state):
        saved.append(state)
        if node=='RootCauseAgent':
            raise RuntimeError('simulated process crash')
    with pytest.raises(RuntimeError):
        investigate(CONTEXT,MockProvider(),checkpoint=crash)
    assert len(saved[-1]['executions'])==6
    state,_=investigate(CONTEXT,MockProvider(),resume=saved[-1])
    assert len(state['executions'])==10
    assert state['validation']['passed']
