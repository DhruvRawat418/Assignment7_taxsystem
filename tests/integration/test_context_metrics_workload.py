"""Ensure the experiment uses each packet and keeps both modes comparable."""
from copy import deepcopy
import pytest
from demo.context_metrics import measure

class Encoding:
    def encode(self, text, **kwargs):
        return list(text)

@pytest.mark.asyncio
async def test_distinct_packets_same_order_and_no_mutation():
    packets = [dict(computation_result={'status': 'completed', 'unique': str(i)},
                    audit_result={'status': 'passed'}, projection_notes=[])
               for i in range(10)]
    original = deepcopy(packets)
    baseline = await measure(packets, enabled=False, live=False, encoding=Encoding())
    bounded = await measure(packets, enabled=True, live=False, encoding=Encoding())
    assert packets == original
    assert len(baseline['rows']) == len(bounded['rows']) == 10
    assert [r['document'] for r in bounded['rows']] == list(range(1, 11))
    assert baseline['rows'][-1]['local_content_tokens'] > bounded['rows'][-1]['local_content_tokens']
    assert all(r['provider_input_tokens'] is None for r in bounded['rows'])
