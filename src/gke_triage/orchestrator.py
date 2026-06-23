from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from gke_triage.models import Finding, TriageResult

_BLOCK_RE = re.compile(r"```STRUCTURED_RESULT\s*(\{.*?\})\s*```", re.DOTALL)

PROMPT_TEMPLATE = (
    "Use the k8s-troubleshooter skill. Investigate workload '{workload}' in "
    "namespace '{namespace}' read-only and emit the STRUCTURED_RESULT block."
)


def parse_structured_result(text: str) -> TriageResult:
    m = _BLOCK_RE.search(text)
    if not m:
        return TriageResult(root_cause="No structured result returned by agent",
                            confidence="low", findings=[], proposed_patch=None)
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return TriageResult(root_cause="Malformed structured result",
                            confidence="low", findings=[], proposed_patch=None)
    findings = [Finding(summary=f.get("summary", ""),
                        evidence=f.get("evidence", []),
                        manifest_path=f.get("manifest_path"))
                for f in data.get("findings", [])]
    return TriageResult(
        root_cause=data.get("root_cause", ""),
        confidence=data.get("confidence", "low"),
        findings=findings,
        proposed_patch=data.get("proposed_patch") or None,
    )


def diagnose(workload: str, namespace: str,
             runner: Callable[[str, Path | None], str],
             workdir: Path | None = None) -> TriageResult:
    prompt = PROMPT_TEMPLATE.format(workload=workload, namespace=namespace)
    output = runner(prompt, workdir)
    return parse_structured_result(output)
