"""Measure ten sequential synthetic review events. No API calls unless --live."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile

from src.agents.adversarial import REVIEW_INSTRUCTIONS, make_adversarial_provider
from src.agents.review_context import ReviewContext
from src.integration.case_service import CaseService

ROOT = Path(__file__).resolve().parents[1]
ANSWERS = dict(filing_status='single',taxpayer_birth_date='March 5, 1955',taxpayer_blind='no',
    has_dependents='no',has_self_employment_income='no',has_rental_income='no',has_capital_gains='no',
    has_foreign_income_or_accounts='no',taxpayer_can_be_claimed_as_dependent='no',wants_to_itemize='no',
    needs_state_return='no',documents='W-2',has_estimated_payments='no',has_direct_schedule_amounts='no')


async def prepare_packet():
    """Real OCR, Rules, MCP and audit; explicit fake reviewer captures test evidence.

    Its temporary case is discarded, never exported as a reviewed submission.
    """
    packets=[]
    async def capture(messages):
        packets.append(json.loads(messages[-1]['content']))
        return {'findings':[]}  # Instrumentation only, never a live-review claim.
    with tempfile.TemporaryDirectory(prefix='silverfile-context-fixture-') as folder:
        service=CaseService(folder);view=service.create('context-fixture')
        for _ in range(50):
            if view['status']=='ready_for_checks':break
            field=view['pending']['field']
            if field=='w2_files':
                image=ROOT/'demo/w2_clean.jpg'
                view=service.upload_w2('context-fixture',view['token'],[(image.name,image.read_bytes())])
            else:
                view=service.answer('context-fixture',view['token'],ANSWERS[field])
        result=await service.run_checks('context-fixture',capture)
        if result['status']!='ready_for_human_review' or len(packets)!=1:
            raise RuntimeError('Synthetic evidence preparation failed; inspect the fixture.')
    return packets[0]


def content_tokens(messages,encoding):
    # This measures real serialized message CONTENT, not hidden provider framing.
    return sum(len(encoding.encode(m['content'],disallowed_special=())) for m in messages)


async def measure(packet,*,enabled,live,encoding):
    context=ReviewContext(REVIEW_INSTRUCTIONS,enabled=enabled)
    usage=[];rows=[]
    if live:
        from src.agents.openai_transport import make_openai_review_call
        transport=make_openai_review_call(usage_callback=usage.append)
    async def measured_model(messages):
        count=content_tokens(messages,encoding)
        before=len(usage)
        if live:
            report=await transport(messages)
        else:
            report={'findings':[]}  # Explicit offline instrumentation response.
        rows.append(dict(document=len(rows)+1,local_content_tokens=count,
            provider_input_tokens=usage[-1]['input_tokens'] if len(usage)>before else None,
            provider_output_tokens=usage[-1]['output_tokens'] if len(usage)>before else None,
            finding_count=len(report.get('findings',[]))))
        return report
    provider=make_adversarial_provider(measured_model,context=context)
    for sequence in range(1,11):
        current=deepcopy(packet)
        # Ten separately indexed synthetic replay events of the same fixture:
        # intentionally fixed evidence size isolates history growth, not accuracy.
        current['projection_notes'].append({'measurement_document':sequence,'synthetic_fixture_replay':True})
        result=await provider(current)
        if result.status!='ready':
            raise RuntimeError(f'Review {sequence} failed; no successful metric is inferred.')
    return dict(strategy='selective_recall' if enabled else 'disabled_full_history',rows=rows)


async def run(args):
    if args.live and not os.getenv('OPENAI_API_KEY'):
        raise ValueError('--live needs your own OPENAI_API_KEY; no fallback or automatic key discovery.')
    try:
        import tiktoken
    except ImportError:
        raise ValueError('Install requirements-metrics.txt before measuring tokens.') from None
    packet=await prepare_packet()
    encoding=tiktoken.get_encoding('o200k_base')
    modes=[False,True] if args.compare else [not args.no_context_strategy]
    runs=[await measure(packet,enabled=mode,live=args.live,encoding=encoding) for mode in modes]
    report=dict(mode='live_api' if args.live else 'offline_local_tokenizer',
        tokenizer='tiktoken 0.12.0 / o200k_base',
        method='Sum of actual message content tokens; excludes roles/framing, response schema and provider overhead.',
        workload='Ten sequential indexed replays of one synthetic W-2-derived review packet, one ReviewContext instance per run.',
        packet_origin='Actual W-2 OCR, Rules, MCP and deterministic Audit; explicit fake reviewer only during packet capture.',
        fixture_sha256=hashlib.sha256((ROOT/'demo/w2_clean.jpg').read_bytes()).hexdigest(),
        live_api_calls=20 if args.live and args.compare else (10 if args.live else 0),runs=runs)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(f'Saved {output}; mode={report["mode"]}; live_api_calls={report["live_api_calls"]}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-context-strategy',action='store_true')
    parser.add_argument('--compare',action='store_true',help='Measure both modes: 20 requests only if --live is also explicit.')
    parser.add_argument('--live',action='store_true',help='Makes paid requests using your own configured key.')
    parser.add_argument('--output',default='outputs/context-metrics.json')
    args=parser.parse_args()
    if args.compare and args.no_context_strategy:parser.error('Choose --compare or --no-context-strategy.')
    try:asyncio.run(run(args))
    except (ValueError,RuntimeError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
