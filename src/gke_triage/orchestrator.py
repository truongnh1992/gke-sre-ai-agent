from __future__ import annotations

import json
import os
import re
import subprocess
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


SKILLS_DIR = Path(__file__).parent / "skills"


def gemini_runner(prompt: str, workdir: Path | None = None) -> str:
    """Run Gemini CLI non-interactively with the skills dir mounted.

    The guardrail MCP server is registered via a Gemini extension config that
    invokes `gke-triage _serve-proxy`. Cluster access therefore always passes
    through the read-only Guardrail.
    """
    env = dict(os.environ)
    env["GEMINI_SKILLS_DIR"] = str(SKILLS_DIR)
    cmd = ["gemini", "-p", prompt]
    result = subprocess.run(
        cmd, cwd=str(workdir) if workdir else None,
        env=env, capture_output=True, text=True,
    )
    return result.stdout


def diagnose(workload: str, namespace: str,
             runner: Callable[[str, Path | None], str],
             workdir: Path | None = None) -> TriageResult:
    prompt = PROMPT_TEMPLATE.format(workload=workload, namespace=namespace)
    output = runner(prompt, workdir)
    return parse_structured_result(output)
