from __future__ import annotations

from pathlib import Path

from gke_scout.models import TriageResult


def render_report(workload: str, namespace: str, result: TriageResult) -> str:
    lines = [
        f"# Triage report: {workload} (namespace: {namespace})",
        "",
        f"**Confidence:** {result.confidence}",
        "",
        "## Root cause",
        "",
        result.root_cause,
        "",
        "## Evidence",
        "",
    ]
    for f in result.findings:
        lines.append(f"### {f.summary}")
        for e in f.evidence:
            lines.append(f"- {e}")
        lines.append("")

    if not result.is_conclusive():
        lines += ["## Inconclusive", "",
                  "Low confidence. Ranked hypotheses above; "
                  "gather more evidence before acting.", ""]
    return "\n".join(lines)


def write_outputs(out_dir: str | Path, workload: str, namespace: str,
                  result: TriageResult) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_name = f"{workload}-report.md"
    (out_dir / report_name).write_text(render_report(workload, namespace, result))

    return {"report": report_name}
