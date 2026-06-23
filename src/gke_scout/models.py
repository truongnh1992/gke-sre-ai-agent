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


@dataclass
class TriageResult:
    root_cause: str
    confidence: str  # "high" | "medium" | "low"
    findings: list[Finding] = field(default_factory=list)

    def is_conclusive(self) -> bool:
        return self.confidence in {"high", "medium"}
