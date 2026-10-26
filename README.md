# Assignment7_taxsystem

## Yong Cai: Review / Audit component (`yong/audit`)

This branch adds **only the first, deterministic Audit component** for SilverFile.
It is not the complete multi-agent application, a tax adviser, an LLM adversarial
reviewer, or permission to file a return. Other agents remain on their owners'
branches; none were merged here.

Python 3.11+; no dependencies or API keys required for the standalone tests:

```bash
python -m unittest discover -s tests -v
python -m demo.run_audit --synthetic-demo
python -m demo.run_audit --synthetic-demo --tamper
```

The first demo uses an explicitly labelled **test-only tool double, not MCP**.
It exits 0 for the synthetic clean packet. The tampered demo exits 1 with
`revision_required`. Do not use that double to validate real returns.

```bash
python -m demo.run_audit path/to/audit_packet.json
```

The packet command has no configured MCP client and intentionally cannot pass.
Integrate a real client using `make_audit_node(client)` as described in
[docs/AUDIT.md](docs/AUDIT.md). That document defines input/output fields, source
bindings, fail-closed status routing, and the remaining integration work.

AI assistance is disclosed in [docs/AI_DISCLOSURE_AUDIT.md](docs/AI_DISCLOSURE_AUDIT.md).
