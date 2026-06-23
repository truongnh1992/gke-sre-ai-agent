from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gke_triage.guardrail.redact import redact
from gke_triage.models import Decision, ToolCall


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, call: ToolCall, decision: Decision) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": call.name,
            "args": redact(call.args),
            "allowed": decision.allowed,
            "reason": decision.reason,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
