"""Ten-node bounded LangGraph with independent validation and durable checkpoint hooks."""
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .agents.specialists import AGENTS, AgentOutput
from .schemas import Investigation


class State(TypedDict):
    context: dict
    proposal: dict
    validation: dict
    history: list[dict]
    iteration: int
    max_iterations: int
    failure: str
    agents: list[dict]
    executions: list[dict]
    controller: dict
    entry: str
    next_node: str


def investigate(context,provider,max_iterations=3,checkpoint=None,resume=None,timeout_seconds=120,independent_validation=True,self_correction=True):
    if not 1<=max_iterations<=3:
        raise ValueError('Maximum iterations must be between 1 and 3')
    if not 1<=timeout_seconds<=600:
        raise ValueError('Workflow timeout must be between 1 and 600 seconds')
    started=time.monotonic()
    graph=StateGraph(State)
    names=[]
    agent_types=[agent for agent in AGENTS if independent_validation or agent.__name__ not in ('IndependentValidationAgent','SelfCorrectionControllerAgent')]
    if not self_correction:
        max_iterations=1
    for agent_type in agent_types:
        agent=agent_type(provider) if agent_type.__name__ in ('CorrectionRecommendationAgent','RootCauseAgent') else agent_type()
        name=agent_type.__name__
        names.append(name)

        def execute(state,agent=agent,name=name):
            before=time.monotonic()
            updates={}
            try:
                if before-started>timeout_seconds:
                    raise TimeoutError('Workflow deadline exceeded')
                output=AgentOutput.model_validate(agent.run(state['context'],state))
                if set(output.evidence_ids)-set(state['context']['transaction_ids']):
                    raise ValueError('Agent referenced evidence outside scope')
                serialized=output.model_dump(mode='json')
                if name=='CorrectionRecommendationAgent':
                    updates={'proposal':output.facts['proposal'],'iteration':state['iteration']+1}
                elif name=='IndependentValidationAgent':
                    updates={'validation':output.facts['validation'],'history':state['history']+[{'iteration':state['iteration'],'proposal':state['proposal'],'validation':output.facts['validation']}]}
                elif name=='SelfCorrectionControllerAgent':
                    updates={'controller':output.facts}
                event={'agent':agent.name,'node':name,'iteration':updates.get('iteration',state['iteration']),
                    'output':serialized,'duration_ms':int((time.monotonic()-before)*1000)}
                updates|={'agents':state['agents']+[serialized],'executions':state['executions']+[event]}
            except Exception as exc:
                updates={'failure':f'{name} failed ({type(exc).__name__}); manual escalation required'}
                if name=='CorrectionRecommendationAgent':
                    updates['iteration']=state['iteration']+1
            if updates.get('failure'):
                updates['next_node']=name
            elif name=='SelfCorrectionControllerAgent':
                updates['next_node']='RootCauseAgent' if updates['controller'].get('retry') else 'DecisionExplanationAgent'
            else:
                position=names.index(name)
                updates['next_node']=names[position+1] if position+1<len(names) else 'complete'
            if checkpoint:
                checkpoint(name,{**state,**updates})
            return updates

        graph.add_node(name,execute)
    graph.add_conditional_edges(START,lambda s:s['entry'],{**{name:name for name in names},'complete':END})
    for index,name in enumerate(names[:-1]):
        if name=='SelfCorrectionControllerAgent':
            graph.add_conditional_edges(name,lambda s:'stop' if s['failure'] else 'revise' if s['controller'].get('retry') else 'explain',
                {'stop':END,'revise':'RootCauseAgent','explain':'DecisionExplanationAgent'})
        else:
            graph.add_conditional_edges(name,lambda s:'stop' if s['failure'] else 'next',{'stop':END,'next':names[index+1]})
    graph.add_edge(names[-1],END)
    initial={'context':context,'proposal':{},'validation':{},'history':[],'iteration':0,'max_iterations':max_iterations,
        'failure':'','agents':[],'executions':[],'controller':{},'entry':names[0],'next_node':names[0]}
    if resume:
        if resume.get('context',{}).get('transaction_ids')!=context['transaction_ids']:
            raise ValueError('Checkpoint evidence does not agree with current scope')
        if resume.get('next_node')=='complete' or resume.get('failure') and resume.get('iteration',0)>=max_iterations:
            return resume,explain(resume)
        if resume.get('context')!=context:
            raise ValueError('Checkpoint context or accounting policy changed; start a fresh investigation')
        initial={**resume,'entry':resume.get('next_node',names[0]),'failure':''}
    state=graph.compile().invoke(initial,config={'recursion_limit':60})
    return state,explain(state)


def explain(state):
    diagnosis=next((a['facts']['diagnosis'] for a in reversed(state['agents']) if 'diagnosis' in a.get('facts',{})),{})
    analysis=Investigation(cause=diagnosis.get('cause','unknown_cause'),alternative_explanations=diagnosis.get('alternative_explanations',[]),
        uncertainty=state.get('proposal',{}).get('uncertainty',[])+([state['failure']] if state['failure'] else []),
        agents=[{k:a[k] for k in ('agent','basis','findings','evidence_ids')} for a in state['agents']])
    return analysis.model_dump(mode='json')
