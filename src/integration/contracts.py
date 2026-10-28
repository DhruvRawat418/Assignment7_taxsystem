"""Integration-only provider contracts. Existing workers keep their own models."""
from dataclasses import dataclass, field
from typing import Callable, Literal


class IntegrationError(ValueError):
    def __init__(self, code="invalid_packet", owner="rules"):
        self.code, self.owner = code, owner
        super().__init__(code)  # Only application-owned codes; never raw exceptions.


@dataclass(frozen=True)
class ProviderResult:
    status: Literal["ready", "not_configured", "needs_input", "needs_human_review", "failed"]
    data: dict = field(default_factory=dict)
    issue_codes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.status not in ("ready", "not_configured", "needs_input", "needs_human_review", "failed"):
            raise IntegrationError("invalid_provider_status", "orchestrator")
        if not isinstance(self.data, dict) or not isinstance(self.issue_codes, tuple):
            raise IntegrationError("invalid_provider_result", "orchestrator")


@dataclass(frozen=True)
class Providers:
    intake: Callable | None = None
    rules: Callable | None = None
    adversarial: Callable | None = None
    extraction: Callable | None = None
    computation: Callable | None = None
    audit: Callable | None = None
    mode: Literal["live", "synthetic"] = "live"

    def readiness(self):
        return {"intake": "configured" if self.intake else "not_configured",
                "rules": "configured" if self.rules else "not_configured",
                "adversarial_review": "configured" if self.adversarial else "not_configured",
                "extraction": "configured" if self.extraction else "existing_adapter",
                "computation": "configured" if self.computation else "existing_mcp_adapter",
                "deterministic_audit": "configured" if self.audit else "existing_mcp_adapter",
                "dashboard": "not_implemented", "form_renderer": "not_implemented"}
