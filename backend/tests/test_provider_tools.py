from types import SimpleNamespace
import pytest
from app.providers import OpenAIProvider,MockProvider
from test_controls import CONTEXT


def fake_client(monkeypatch,tool_ids):
    calls=[]
    class Message:
        tool_calls=[SimpleNamespace(id='tool-1',function=SimpleNamespace(name='get_financial_evidence',arguments=__import__('json').dumps({'ids':tool_ids})))]
        def model_dump(self,**kwargs):
            return {'role':'assistant','content':None,'tool_calls':[{'id':'tool-1','type':'function','function':{'name':'get_financial_evidence','arguments':self.tool_calls[0].function.arguments}}]}
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=Message())],usage=None)
    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=MockProvider().propose(CONTEXT,[])))],usage=None)
    monkeypatch.setenv('OPENAI_API_KEY','offline-test-placeholder')
    import openai
    monkeypatch.setattr(openai,'OpenAI',lambda **kwargs:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create,parse=parse))))
    return calls


def test_function_tool_is_readonly_scoped_and_bounded(monkeypatch):
    calls=fake_client(monkeypatch,['bank-fee'])
    context=CONTEXT|{'evidence_records':[{'id':'bank-fee','amount':'-25','currency':'USD'}]}
    assert OpenAIProvider().propose(context,[]).action=='draft_journal'
    assert len(calls)==2
    assert calls[0]['tools'][0]['function']['name']=='get_financial_evidence'
    assert not calls[0]['parallel_tool_calls']
    assert calls[1]['messages'][-1]['role']=='tool'


def test_provider_cannot_retrieve_out_of_scope_records(monkeypatch):
    calls=fake_client(monkeypatch,['other-tenant-record'])
    with pytest.raises(ValueError,match='outside exception scope'):
        OpenAIProvider().propose(CONTEXT|{'evidence_records':[{'id':'bank-fee'}]},[])
    assert len(calls)==1


def test_structured_correction_has_closed_object_schemas():
    from openai.lib._pydantic import to_strict_json_schema
    from app.schemas import Correction
    schema=to_strict_json_schema(Correction)
    assert schema['additionalProperties'] is False
    for definition in schema.get('$defs',{}).values():
        if definition.get('type')=='object':
            assert definition.get('additionalProperties') is False
