"""Reference corpus for Eligibility & Rules; no arithmetic and no dialogue.

Every clearance citation and every box disposition names an id defined here.
`cite()` raises on an unknown id, so a determination carrying an invented
authority cannot be constructed. Replace the `source` strings if the course
supplies its own corpus; the agent depends only on the ids.
"""
from dataclasses import dataclass

TAX_YEAR = 2025


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    text: str
    source: str


class UnknownRuleError(KeyError):
    """Raised when a citation names a rule that is not in the corpus."""


_RULES = (
    Rule("DEP-01", "Dependent transcription",
         "Dependent names, synthetic SSNs and relationships are transcribed from intake. Other values, including credits, are direct sourced inputs; do not infer credits from a name or relationship.", "Assignment brief 3.1"),
    Rule("DEP-02", "Dependent attachment review",
         "The supplied 2025 template has four dependent columns. More than four requires staff handling of an attachment; do not truncate the list.", "2025 Form 1040-SR page 1 dependent section"),
    Rule("SR-ELIG-01", "1040-SR age eligibility",
         "For tax year 2025 the taxpayer must have been born before 2 January 1961 to file on "
         "Form 1040-SR.", "Assignment brief 3.2(1)"),
    Rule("SR-ELIG-02", "Joint return age test",
         "On a joint return only one spouse needs to meet the 1040-SR age test.",
         "Assignment brief 3.2(1)"),
    Rule("SR-ELIG-03", "No income restriction",
         "There is no income restriction on the use of Form 1040-SR.", "Assignment brief 3.2(1)"),
    Rule("FS-01", "Permitted filing statuses",
         "All five filing statuses are in scope: single; married filing jointly; married filing "
         "separately; head of household; qualifying surviving spouse.", "Assignment brief 3.3"),
    Rule("FS-02", "Filing status ambiguity escalates",
         "Filing-status ambiguity must be routed to a human. A spouse who died during the tax "
         "year is the central case, because the correct status may be married filing jointly, "
         "qualifying surviving spouse, or single.", "Assignment brief 4.4(5)"),
    Rule("FS-03", "Joint return requires spouse details",
         "A joint return requires spouse age and blindness information before the deduction "
         "lines can be determined.", "Assignment brief 3.1 line 12d"),
    Rule("FS-04", "Separate return living arrangement",
         "A married filing separately return requires whether the taxpayer lived with the spouse "
         "during the year, because Social Security taxation depends on that answer.",
         "Assignment brief 3.2(4)"),
    Rule("SD-01", "Base standard deduction amounts",
         "The 2025 base standard deduction amounts are 15,750 for single and married filing "
         "separately, 31,500 for married filing jointly and qualifying surviving spouse, and "
         "23,625 for head of household.", "Assignment brief 3.2(2)"),
    Rule("SD-02", "Line 12d box definitions",
         "Count one box each for taxpayer 65 or older, taxpayer blind, spouse 65 or older, and "
         "spouse blind.", "Assignment brief 3.2(2)"),
    Rule("SD-03", "Additional amount per checked box",
         "Each checked box on line 12d adds 2,000 if the taxpayer is unmarried and not a "
         "surviving spouse, and 1,600 otherwise.", "Assignment brief 3.2(2)"),
    Rule("SD-04", "Standard Deduction Chart does not apply",
         "The chart does not apply, and the return escalates, if the taxpayer can be claimed as "
         "a dependent, if a separately-filing spouse itemises, or if the taxpayer was a "
         "dual-status alien.", "Assignment brief 3.2(2)"),
    Rule("SD-05", "Standard deduction only",
         "Only the standard deduction is in scope. Itemised deductions on Schedule A are out of "
         "scope.", "Assignment brief 3.3"),
    Rule("SD-06", "Spouse boxes on a separate return",
         "Counting spouse age or blindness boxes on a married filing separately return requires "
         "explicit approval, because it depends on facts outside the stated scope.",
         "Assignment brief 3.2(2)"),
    Rule("ESD-01", "Enhanced senior deduction, qualifying persons",
         "An additional deduction of 6,000 is available per qualifying person aged 65 or older, "
         "or 12,000 where both spouses on a joint return qualify.", "Assignment brief 3.2(3)"),
    Rule("ESD-02", "Enhanced senior deduction phase-out",
         "The deduction phases out above 75,000 modified adjusted gross income, or 150,000 on a "
         "joint return, at 6 percent of the excess, applied per qualifying individual.",
         "Assignment brief 3.2(3)"),
    Rule("ESD-03", "Enhanced senior deduction is additive",
         "The enhanced senior deduction is in addition to the additional standard deduction for "
         "age and blindness. Conflating the two is a known error.", "Assignment brief 3.2(3)"),
    Rule("ESD-04", "Enhanced senior deduction reporting",
         "The deduction is claimed on Schedule 1-A and carried to line 13b. It applies to tax "
         "years 2025 through 2028.", "Assignment brief 3.2(3) and 3.1 line 13b"),
    Rule("SSA-01", "Taxable Social Security ordering dependency",
         "Only part of Social Security benefits is taxable, determined by a worksheet over "
         "provisional income. The worksheet requires the rest of income before it can run, and "
         "its result feeds adjusted gross income.", "Assignment brief 3.2(4)"),
    Rule("SCOPE-01", "In-scope documents",
         "Amounts from Form W-2, SSA-1099, 1099-R, 1099-INT and 1099-DIV are in scope.",
         "Assignment brief 3.3"),
    Rule("SCOPE-02", "Itemised deductions out of scope",
         "Itemised deductions on Schedule A are out of scope and escalate.",
         "Assignment brief 3.3"),
    Rule("SCOPE-03", "Self-employment and business income out of scope",
         "Self-employment or business income on Schedule C, including 1099-NEC nonemployee "
         "compensation, is out of scope and escalates.", "Assignment brief 3.3"),
    Rule("SCOPE-04", "Rental income out of scope",
         "Rental income on Schedule E is out of scope and escalates.", "Assignment brief 3.3"),
    Rule("SCOPE-05", "Capital gains and digital assets out of scope",
         "Capital gains requiring Schedule D, and digital assets, are out of scope and escalate.",
         "Assignment brief 3.3"),
    Rule("SCOPE-06", "Foreign income and accounts out of scope",
         "Foreign income or foreign accounts are out of scope and escalate.",
         "Assignment brief 3.3"),
    Rule("SCOPE-07", "Amended, prior-year and state returns out of scope",
         "Amended returns, prior-year returns and state returns are out of scope and escalate.",
         "Assignment brief 3.3"),
    Rule("SCOPE-08", "1099-R with taxable amount not determined",
         "Any 1099-R with box 2b taxable amount not determined escalates. Deriving the taxable "
         "portion needs the Simplified Method or the General Rule, and neither is in scope.",
         "Assignment brief 3.3 and 4.4(3)"),
    Rule("SCHED-01", "Schedules 1, 2 and 3",
         "Schedules 1, 2 and 3 are in scope as direct user input. The system does not derive "
         "their values.", "Assignment brief 3.3"),
    # W-2 box dispositions. Every extracted box needs an explicit decision; the
    # integration adapter rejects a document with any box left unaccounted for.
    Rule("W2-BOX-01", "W-2 box 1 to line 1z",
         "Wages, tips and other compensation in box 1 are reported on Form 1040-SR line 1z.",
         "Assignment brief 3.1 line 1z"),
    Rule("W2-BOX-02", "W-2 box 2 to line 25a",
         "Federal income tax withheld in box 2 is reported on Form 1040-SR line 25a.",
         "Assignment brief 3.1 line 25a"),
    Rule("W2-BOX-03", "Social Security and Medicare boxes are not return lines",
         "Social Security and Medicare wages, tips and withholding, in boxes 3 through 7, are "
         "not reported on Form 1040-SR. They are not income and not a credit against income "
         "tax.", "Assignment brief 3.1"),
    Rule("W2-BOX-04", "Informational W-2 boxes are not return lines",
         "Dependent care benefits, nonqualified plans, coded box 12 entries, the box 13 "
         "checkboxes and other-information box 14 are informational for this scope and are not "
         "reported on Form 1040-SR.", "Assignment brief 3.1 and 3.3"),
    Rule("W2-BOX-05", "State and local W-2 boxes are out of scope",
         "State and local wages and withholding, in boxes 15 through 20, belong to a state "
         "return, which is out of scope.", "Assignment brief 3.3"),
    Rule("W2-BOX-06", "Identification boxes carry no amount",
         "Employer and employee identification boxes carry no amount to any Form 1040-SR line.",
         "Assignment brief 3.1"),
    Rule("SSN-01", "Test Social Security numbers only",
         "Only Social Security numbers with an area number from 900 through 999 may be accepted. "
         "Any other value must be rejected so that a real number is never captured.",
         "Assignment brief 3.2"),
    Rule("ADVICE-01", "No tax advice",
         "The system does not give tax advice, planning or optimisation. Such requests escalate. "
         "Transcription and arithmetic are not advice.", "Assignment brief 2 and 4.4(4)"),
    Rule("HITL-01", "Escalation on conflict",
         "Any unresolved conflict between a user statement and a document escalates to a human.",
         "Assignment brief 4.4(2)"),
    Rule("HITL-02", "Escalation on exploitation signals",
         "Any indication of financial exploitation or third-party pressure escalates. The system "
         "notices and stops; it does not adjudicate.", "Assignment brief 4.4(6)"),
    Rule("HITL-03", "Honest uncertainty",
         "Flagging a question for a human is a correct outcome. The system does not guess when a "
         "rule is unclear.", "Assignment brief 4.3"),
)

RULES = {rule.id: rule for rule in _RULES}

# Explicit disposition for every W-2 box this scope recognises. A box that is
# not listed is escalated rather than silently dropped: a box nobody has
# classified might be taxable, and guessing is the failure mode that matters.
W2_LINE_BOXES = {"1": "1z", "2": "25a"}
W2_NOT_USED = {
    "3": "W2-BOX-03", "4": "W2-BOX-03", "5": "W2-BOX-03", "6": "W2-BOX-03", "7": "W2-BOX-03",
    "8": "W2-BOX-04", "9": "W2-BOX-04", "10": "W2-BOX-04", "11": "W2-BOX-04", "12": "W2-BOX-04",
    "13": "W2-BOX-04", "14": "W2-BOX-04",
    "15": "W2-BOX-05", "16": "W2-BOX-05", "17": "W2-BOX-05", "18": "W2-BOX-05",
    "19": "W2-BOX-05", "20": "W2-BOX-05",
    "a": "W2-BOX-06", "b": "W2-BOX-06", "c": "W2-BOX-06", "d": "W2-BOX-06",
    "e": "W2-BOX-06", "f": "W2-BOX-06",
}


def get_rule(rule_id):
    try:
        return RULES[rule_id]
    except KeyError:
        raise UnknownRuleError(f"{rule_id!r} is not in the reference corpus") from None


def cite(*rule_ids):
    """Return citation ids, raising if any is not in the corpus."""
    if not rule_ids:
        raise UnknownRuleError("a determination must cite at least one rule")
    return [get_rule(rule_id).id for rule_id in rule_ids]


def describe(rule_id):
    rule = get_rule(rule_id)
    return dict(rule_id=rule.id, title=rule.title, text=rule.text, source=rule.source)


def validate_rule_ids(rule_ids):
    """Split ids into (known, unknown). Applied to anything a model returns."""
    return ([r for r in rule_ids if r in RULES], [r for r in rule_ids if r not in RULES])


def corpus_for_prompt(prefix=None):
    return "\n".join(f"{r.id}: {r.title}. {r.text}" for r in _RULES
                     if prefix is None or r.id.startswith(prefix))
