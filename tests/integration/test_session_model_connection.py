"""Explicit credentials stay outside global environment and saved case data."""
import os
from types import SimpleNamespace
import pytest
from src.agents.adversarial_contract import ReviewReport


@pytest.mark.asyncio
async def test_explicit_key_is_bound_to_client_without_environment_mutation(monkeypatch):
    from src.agents import openai_transport as transport
    before=os.environ.get('OPENAI_API_KEY')
    captured=[]
    class Client:
        def __init__(self,**kwargs):
            captured.append(kwargs)
            self.responses=SimpleNamespace(parse=self.parse)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def parse(self,**kwargs):
            assert 'session-private-key' not in repr(kwargs)
            return SimpleNamespace(status='completed',output_parsed=ReviewReport(findings=[]))
    monkeypatch.setattr(transport,'AsyncOpenAI',Client)
    call=transport.make_openai_review_call(api_key='session-private-key')
    assert await call([{'role':'user','content':'Synthetic evidence'}])=={'findings':[]}
    assert captured[0]['api_key']=='session-private-key'
    assert os.environ.get('OPENAI_API_KEY')==before
