"""Actual reviewer messages use selective recall; baseline retains prior evidence."""
import json
import pytest
from importlib import import_module


def context(**kwargs):
    return import_module('src.agents.review_context').ReviewContext('Instructions',**kwargs)


def test_selective_recall_contains_current_evidence_and_decision_summary_only():
    c=context()
    old=c.messages({'document':'old-sensitive-fixture'})
    c.record(old,{'findings':[]})
    current=c.messages({'document':'current-fixture'})
    assert json.loads(current[-1]['content'])=={'document':'current-fixture'}
    assert 'old-sensitive-fixture' not in str(current)
    assert 'Previous reviews: 1' in current[0]['content']


def test_disabled_strategy_actually_sends_earlier_request_and_response():
    c=context(enabled=False)
    old=c.messages({'document':'old-fixture'})
    c.record(old,{'findings':[]})
    current=c.messages({'document':'current-fixture'})
    assert len(current)==4
    assert 'old-fixture' in current[1]['content']
    assert json.loads(current[-1]['content'])=={'document':'current-fixture'}


def test_context_is_bounded_and_rejects_nonfinite_packets():
    c=context()
    with pytest.raises(ValueError):c.messages({'amount':float('nan')})
    with pytest.raises(ValueError):c.messages({'large':'x'*200001})
    for _ in range(10):
        messages=c.messages({'document':'fixture'})
        c.record(messages,{'findings':[]})
    with pytest.raises(ValueError):c.messages({'document':'eleventh'})
