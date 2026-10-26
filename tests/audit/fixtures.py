"""Hand-checked synthetic case; no live taxpayer data or production helpers."""
from copy import deepcopy

INPUTS = ("1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a",
          "8", "10", "17", "19", "20", "23", "25a", "25b", "25c", "26", "32", "ss_adjustments")
DERIVED = [
    ("income_before_ss", "sum_amounts", ["1z", "2b", "3b", "4b", "5b", "8"], "50000.00"),
    ("6b", "social_security_taxable", ["6a", "income_before_ss", "2a", "ss_adjustments"], "0.00"),
    ("9", "sum_amounts", ["income_before_ss", "6b"], "50000.00"),
    ("11a", "difference", ["9", "10"], "50000.00"),
    ("11b", "sum_amounts", ["11a"], "50000.00"),
    ("12e", "standard_deduction", [], "17750.00"),
    ("13b", "senior_deduction", ["11b"], "6000.00"),
    ("14", "sum_amounts", ["12e", "13b"], "23750.00"),
    ("15", "difference", ["11b", "14"], "26250.00"),
    ("16", "income_tax", ["15", "3a"], "2911.50"),
    ("18", "sum_amounts", ["16", "17"], "2911.50"),
    ("21", "sum_amounts", ["19", "20"], "0.00"),
    ("22", "difference", ["18", "21"], "2911.50"),
    ("24", "sum_amounts", ["22", "23"], "2911.50"),
    ("25d", "sum_amounts", ["25a", "25b", "25c"], "4000.00"),
    ("33", "sum_amounts", ["25d", "26", "32"], "4000.00"),
    ("34", "difference", ["33", "24"], "1088.50"),
    ("37", "difference", ["24", "33"], "0.00"),
]


def clean_state():
    profile = dict(filing_status="single", taxpayer_65_or_older=True, taxpayer_blind=False,
                   spouse_65_or_older=False, spouse_blind=False)
    tool_profile = dict(profile, mfs_lived_with_spouse=None, mfs_spouse_allowance_approved=False)
    amounts, all_lines, calls = {}, {}, []
    for key in INPUTS:
        value = {"1z": "50000.00", "25a": "4000.00"}.get(key, "0.00")
        source = dict(kind="user_input", reference="synthetic-intake", field="confirmed " + key,
                      entered_by="demo-user", recorded_at="2026-10-24T00:00:00Z")
        if key in ("1z", "25a"):
            source = dict(kind="document", reference="synthetic-w2", field="box 1" if key == "1z" else "box 2")
        amounts[key] = [{"value": value, "sources": [source]}]
        all_lines[key] = dict(value=value, tool_call_id="call-" + key, depends_on=[],
                              sources=[deepcopy(source)], rule_references=["synthetic-rule"])
        calls.append(dict(call_id="call-" + key, output_key=key, tool="sum_amounts",
                          arguments={"values": [value]}, result={"value": value, "rule_references": ["synthetic-rule"]}))
    for key, tool, deps, value in DERIVED:
        vals = [all_lines[d]["value"] for d in deps]
        args = {"values": vals}
        if tool == "difference":
            args = dict(left=vals[0], right=vals[1], floor_zero=key in ("15", "22", "34", "37"))
        elif tool == "social_security_taxable":
            args = dict(benefits=vals[0], other_income=vals[1], tax_exempt_interest=vals[2], adjustments=vals[3], profile=deepcopy(tool_profile))
        elif tool == "standard_deduction":
            args = {"profile": deepcopy(tool_profile)}
        elif tool == "senior_deduction":
            args = {"agi": vals[0], "profile": deepcopy(tool_profile)}
        elif tool == "income_tax":
            args = dict(taxable_income=vals[0], qualified_dividends=vals[1], filing_status="single")
        sources = []
        for dependency in deps:
            for source in all_lines[dependency]["sources"]:
                if source not in sources:
                    sources.append(deepcopy(source))
        all_lines[key] = dict(value=value, tool_call_id="call-" + key, depends_on=deps[:], sources=sources,
                              rule_references=["synthetic-rule"])
        calls.append(dict(call_id="call-" + key, output_key=key, tool=tool, arguments=args,
                          result={"value": value, "rule_references": ["synthetic-rule"]}))
    extraction_source = dict(document_id="w2-1", sha256="a" * 64, page=1, bbox=[0, 0, 10, 10],
                             image_size=[100, 100], raw_text="synthetic", confidence=1.0,
                             agent="document_extraction", engine="test-only", timestamp="2026-10-24T00:00:00Z")
    facts = {"box_1": {"value": "50000.00", "origin": "document", "source": dict(extraction_source, box="1")},
             "box_2": {"value": "4000.00", "origin": "document", "source": dict(extraction_source, box="2")}}
    return dict(
        computation_input=dict(tax_year=2025, profile=profile,
                               rules=dict(approved=True, citations=["synthetic-rule"], blocking_conditions=[]), amounts=amounts),
        computation_result=dict(status="completed", tax_year=2025, draft_only=True,
                                lines={k: v for k, v in all_lines.items() if k not in ("income_before_ss", "ss_adjustments")},
                                intermediates={k: all_lines[k] for k in ("income_before_ss", "ss_adjustments")},
                                tool_calls=calls, issues=[]),
        extractions={"w2-1": dict(document_id="w2-1", sha256="a" * 64, status="extracted", issues=[],
                                  record=dict(document_type="W-2", tax_year={"value": "2025"}, amounts=facts))},
        audit_source_bindings=[dict(reference="synthetic-w2", field="box 1", document_id="w2-1", amount_key="box_1"),
                               dict(reference="synthetic-w2", field="box 2", document_id="w2-1", amount_key="box_2")],
    )


def aliased_duplicate_state():
    """Two input aliases refer to ONE $25k fact, not two independent W-2s."""
    state = clean_state()
    request, result = state["computation_input"], state["computation_result"]
    original = deepcopy(request["amounts"]["1z"][0]["sources"][0])
    alias = dict(original, reference="second-alias-for-same-w2")
    request["amounts"]["1z"] = [dict(value="25000.00", sources=[original]),
                                 dict(value="25000.00", sources=[alias])]
    state["audit_source_bindings"].append(dict(reference=alias["reference"], field=alias["field"],
                                              document_id="w2-1", amount_key="box_1"))
    state["extractions"]["w2-1"]["record"]["amounts"]["box_1"]["value"] = "25000.00"
    result["tool_calls"][0]["arguments"]["values"] = ["25000.00", "25000.00"]
    for line in [*result["lines"].values(), *result["intermediates"].values()]:
        if original in line["sources"]:
            line["sources"].append(deepcopy(alias))
    return state
