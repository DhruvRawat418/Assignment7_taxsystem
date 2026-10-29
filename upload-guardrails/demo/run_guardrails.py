"""Guardrail conformance report. Deterministic; no model, network or API key.

Prints what the system currently promises not to do, which component enforces
each promise, and whether that enforcement fires here. Absent components are
reported as absent rather than counted as passes.
"""
import argparse
import json
import sys

from src.guardrails import probes
from src.guardrails.probes import Outcome
from src.guardrails.redteam import all_cases, run_all, run_case, summary
from src.guardrails.registry import Kind, Status, all_guardrails

MARK = {Outcome.PASS: "pass", Outcome.FAIL: "FAIL", Outcome.ABSENT: "absent"}
SECTION = {
    Kind.PROHIBITION: "Standing prohibitions (assignment 2)",
    Kind.IDENTIFIER: "Identifiers (assignment 3.2)",
    Kind.ESCALATION: "Escalation to a human (assignment 4.4)",
    Kind.ORCHESTRATION: "Orchestration safety (assignment 4.1)",
}


def conformance():
    rows = []
    for guardrail in all_guardrails():
        result = probes.run(guardrail.probe)
        rows.append((guardrail, result))
    return rows


def print_conformance(rows, verbose=False):
    for kind in (Kind.PROHIBITION, Kind.IDENTIFIER, Kind.ESCALATION,
                 Kind.ORCHESTRATION):
        selected = [(g, r) for g, r in rows if g.kind is kind]
        if not selected:
            continue
        print(f"\n{SECTION[kind]}")
        print("-" * len(SECTION[kind]))
        for guardrail, result in selected:
            print(f"  {guardrail.id:3} {MARK[result.outcome]:7} "
                  f"[{guardrail.status.value:8}] {guardrail.statement}")
            if verbose:
                print(f"      owner: {guardrail.owner}")
                print(f"      probe: {result.detail}")
                for point in guardrail.enforcement_points:
                    print(f"      enforced at: {point}")
                if guardrail.note:
                    print(f"      note: {guardrail.note}")


def print_redteam(results, verbose=False):
    print("\nRed team: can a guardrail be talked out of firing?")
    print("-" * 49)
    for result in results:
        case = result.case
        flag = " (intake-dependent)" if case.intake_dependent else ""
        print(f"  {case.id} {MARK[result.outcome]:7} {case.guardrail:3} "
              f"\"{case.phrasing[:58]}\"{flag}")
        if verbose:
            print(f"      {case.rationale}")
            if result.codes:
                print(f"      codes: {', '.join(result.codes)}")


def totals(rows, red):
    passed = sum(1 for _, r in rows if r.outcome is Outcome.PASS)
    failed = sum(1 for _, r in rows if r.outcome is Outcome.FAIL)
    absent = sum(1 for _, r in rows if r.outcome is Outcome.ABSENT)
    counts = summary(red)
    return dict(
        guardrails=len(rows), guardrails_pass=passed, guardrails_fail=failed,
        guardrails_absent=absent,
        recorded_enforced=sum(1 for g, _ in rows if g.status is Status.ENFORCED),
        recorded_partial=sum(1 for g, _ in rows if g.status is Status.PARTIAL),
        recorded_open=sum(1 for g, _ in rows if g.status is Status.OPEN),
        redteam=counts["total"], redteam_pass=counts["pass"],
        redteam_fail=counts["fail"], redteam_absent=counts["absent"],
        redteam_intake_dependent=counts["intake_dependent"],
    )


def as_json(rows, red):
    return dict(
        summary=totals(rows, red),
        guardrails=[dict(id=g.id, kind=g.kind.value, statement=g.statement,
                         source=g.source, owner=g.owner,
                         recorded_status=g.status.value,
                         enforcement_points=list(g.enforcement_points),
                         probe_outcome=r.outcome.value, probe_detail=r.detail,
                         note=g.note)
                    for g, r in rows],
        red_team=[dict(id=r.case.id, guardrail=r.case.guardrail,
                       section=r.case.section, phrasing=r.case.phrasing,
                       intake_dependent=r.case.intake_dependent,
                       outcome=r.outcome.value, detail=r.detail,
                       codes=list(r.codes))
                  for r in red],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redteam", action="store_true",
                        help="Run only the adversarial corpus")
    parser.add_argument("--case", help="Run one red-team case by id, e.g. RT-12")
    parser.add_argument("--json", action="store_true",
                        help="Emit the full report as JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show probe detail, enforcement points and rationale")
    args = parser.parse_args(argv)

    if args.case:
        case = next((c for c in all_cases() if c.id == args.case.upper()), None)
        if case is None:
            parser.error(f"no red-team case {args.case!r}")
            return 2
        result = run_case(case)
        print(f"{case.id} [{case.guardrail}, assignment {case.section}]")
        print(f'  taxpayer says: "{case.phrasing}"')
        print(f"  why it is adversarial: {case.rationale}")
        print(f"  intake must set: {case.intake_sets or 'nothing — structural guardrail'}")
        print(f"  outcome: {MARK[result.outcome]} — {result.detail}")
        if result.codes:
            print(f"  codes: {', '.join(result.codes)}")
        return 0 if result.outcome is not Outcome.FAIL else 1

    rows = [] if args.redteam else conformance()
    red = run_all()

    if args.json:
        print(json.dumps(as_json(rows or conformance(), red), indent=2))
        return 0

    if rows:
        print_conformance(rows, args.verbose)
    print_redteam(red, args.verbose)

    counts = totals(rows or conformance(), red)
    print("\nSummary")
    print("-------")
    print(f"  guardrails: {counts['guardrails_pass']} pass, "
          f"{counts['guardrails_fail']} fail, {counts['guardrails_absent']} absent "
          f"(of {counts['guardrails']})")
    print(f"  recorded:   {counts['recorded_enforced']} enforced, "
          f"{counts['recorded_partial']} partial, {counts['recorded_open']} open")
    print(f"  red team:   {counts['redteam_pass']} pass, {counts['redteam_fail']} fail, "
          f"{counts['redteam_absent']} not exercised (of {counts['redteam']})")
    print(f"  {counts['redteam_intake_dependent']} red-team cases depend on Intake "
          "recognising the phrasing; a pass here does not prove that.")
    if counts["guardrails_absent"] or counts["redteam_absent"]:
        print("  absent is not a pass: those components are not in this checkout.")

    return 1 if counts["guardrails_fail"] or counts["redteam_fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
