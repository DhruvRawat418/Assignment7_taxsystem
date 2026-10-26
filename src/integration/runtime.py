"""Existing workers, with MCP sessions scoped to each invocation, not state."""
from dataclasses import replace
from src.integration.contracts import Providers


def default_runtime(providers=None):
    from src.agents.document_extraction import make_extraction_node
    from src.agents.computation import computation_node, computation_tools
    from src.agents.audit import audit
    async def review(packet):
        async with computation_tools() as client:
            return {"audit_result": await audit(packet, client)}
    p = providers or Providers()
    return replace(p, extraction=p.extraction or make_extraction_node(),
                   computation=p.computation or computation_node, audit=p.audit or review)
