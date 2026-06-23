from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


@dataclass
class Finding:
    summary: str
    evidence: list[str] = field(default_factory=list)
    manifest_path: str | None = None


@dataclass
class TriageResult:
    root_cause: str
    confidence: str  # "high" | "medium" | "low"
    findings: list[Finding] = field(default_factory=list)
    proposed_patch: str | None = None

    def is_conclusive(self) -> bool:
        return bool(self.proposed_patch) and self.confidence in {"high", "medium"}
