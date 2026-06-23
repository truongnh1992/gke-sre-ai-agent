from __future__ import annotations

from typing import Protocol

from gke_triage.guardrail.audit import AuditLog
from gke_triage.guardrail.policy import evaluate
from gke_triage.guardrail.redact import redact
from gke_triage.models import ToolCall


class Upstream(Protocol):
    def call(self, call: ToolCall): ...


class Guardrail:
    """Enforces read-only policy, redacts outputs, and audits every tool call."""

    def __init__(self, upstream: Upstream, audit: AuditLog):
        self.upstream = upstream
        self.audit = audit

    def enforce(self, call: ToolCall):
        decision = evaluate(call)
        self.audit.record(call, decision)
        if not decision.allowed:
            return {"error": f"Tool call refused: {decision.reason}"}
        result = self.upstream.call(call)
        return redact(result)
