"""The integrated harness must not report success when a checked boundary fails."""
import json
from pydantic import Field
from demo import run_guardrails
from src.guardrails import probes
from src.guardrails.probes import Outcome, ProbeResult
from src.guardrails.redteam import all_cases, run_case
from src.guardrails.registry import get


def test_json_report_exits_nonzero_for_a_failed_guardrail(monkeypatch,capsys):
 monkeypatch.setattr(run_guardrails,'conformance',lambda:[(get('P1'),ProbeResult(Outcome.FAIL,'synthetic failed check'))])
 assert run_guardrails.main(['--json'])==1
 assert json.loads(capsys.readouterr().out)['summary']['guardrails_fail']==1


def test_structural_redteam_ssn_case_checks_the_validator(monkeypatch):
 from src.document_extraction import validation
 monkeypatch.setattr(validation,'validate_synthetic_ssn',lambda value:None)
 case=next(c for c in all_cases() if c.id=='RT-16')
 assert run_case(case).outcome is Outcome.FAIL


def test_structural_redteam_amount_case_checks_source_contract(monkeypatch):
 from src.agents import computation_contract
 class UnsourcedAllowed(computation_contract.SourcedAmount):
  sources:list[computation_contract.Source]=Field(default_factory=list)
 monkeypatch.setattr(computation_contract,'SourcedAmount',UnsourcedAllowed)
 case=next(c for c in all_cases() if c.id=='RT-15')
 assert run_case(case).outcome is Outcome.FAIL


def test_1099r_probe_checks_intake_flag_then_rules_block(monkeypatch):
 from src.agents import intake_contract
 assert probes.probe_1099r_rule().outcome is Outcome.PASS
 original=intake_contract._facts
 def lost_box_flag(session):
  facts=original(session);facts['free_text_notes']=[];return facts
 monkeypatch.setattr(intake_contract,'_facts',lost_box_flag)
 assert probes.probe_1099r_rule().outcome is Outcome.FAIL
