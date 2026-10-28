"""Runtime lifecycle checks; actual MCP execution is covered by CLI tests."""
from contextlib import asynccontextmanager
import pytest
from src.integration.contracts import Providers
from src.integration.runtime import default_runtime


def test_default_adapters_do_not_invent_missing_business_providers():
    p = default_runtime()
    assert p.intake is p.rules is p.adversarial is None
    assert all(callable(f) for f in (p.extraction, p.computation, p.audit))


@pytest.mark.asyncio
async def test_audit_runtime_closes_and_reacquires_client_even_after_error(monkeypatch):
    import src.agents.computation as computation_module
    import src.agents.audit as audit_module
    opened, closed = [], []

    @asynccontextmanager
    async def connection():
        client = object()
        opened.append(client)
        try:
            yield client
        finally:
            closed.append(client)

    async def review(packet, client):
        if packet.get("fail"):
            raise RuntimeError("test-only failure")
        return {"status": "test_only", "no_client_in_state": True}

    monkeypatch.setattr(computation_module, "computation_tools", connection)
    monkeypatch.setattr(audit_module, "audit", review)
    runtime = default_runtime(Providers())
    with pytest.raises(RuntimeError):
        await runtime.audit({"fail": True})
    result = await runtime.audit({})
    assert len(opened) == 2 and opened[0] is not opened[1]
    assert closed == opened
    assert result == {"audit_result": {"status": "test_only", "no_client_in_state": True}}
