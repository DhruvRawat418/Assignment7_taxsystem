# AI-use disclosure: ENMGT 5405 Assignment 7 Eligibility & Rules component

Claude (Anthropic) assisted Jijuan Xu with interpreting the assignment and developing the eligibility & rules boundaries. Claude also aided with drafting and revising the Python implementation, the reference corpus, synthetic fixtures, automated tests, the component demo and this documentation, and running development checks. This is substantial AI assistance. 

The implemented component is deterministic and makes no LLM calls on the path
that produces a determination. One optional classifier, `scope_sentinel`,
would call a model to classify free-text intake notes; it is not configured by
default, its output is constrained to reference-corpus ids and re-validated,
and anything unverifiable escalates to a human rather than deciding. The test
suite and both demo modes run with no model and no API key.

The team must validate the adapters end to end, finish the
adversarial reviewer, HITL surface and dashboard, extend the box-disposition
tables when extraction supports forms beyond the W-2, and confirm the rule
corpus against whatever reference material the course supplies.

No original taxpayer records, credentials or actual Social Security numbers
were supplied in these fixtures; every identifier is a 900-series test value.
No paid model was called to generate demo tax answers.
