"""Bounded, per-batch review context. Never share an instance across taxpayers."""
from copy import deepcopy
import json


class ReviewContext:
    def __init__(self, instructions, *, enabled=True):
        self.instructions = instructions
        self.enabled = enabled
        self.completed = 0
        self.reports_with_findings = 0
        self._history = []

    def messages(self, packet):
        if self.completed >= 10:
            raise ValueError('Start a new review batch after ten documents.')
        evidence = json.dumps(packet, allow_nan=False)
        if len(evidence.encode('utf-8')) > 200_000:
            raise ValueError('Review packet is too large.')
        instructions = self.instructions
        if self.enabled and self.completed:
            instructions += (f'\nPrevious reviews: {self.completed}. Reports with findings: '
                             f'{self.reports_with_findings}. Earlier results do not approve the current document.')
        messages = [{'role':'system','content':instructions}]
        if not self.enabled:
            messages.extend(deepcopy(self._history))
        messages.append({'role':'user','content':evidence})
        if len(json.dumps(messages).encode('utf-8')) > 2_500_000:
            raise ValueError('Review context budget exceeded.')
        return messages

    def record(self, messages, report):
        # The caller records only a successfully validated ReviewReport.
        if not self.enabled:
            self._history.extend([deepcopy(messages[-1]),
                                  {'role':'assistant','content':json.dumps(report,allow_nan=False)}])
        self.completed += 1
        self.reports_with_findings += bool(report['findings'])
