from __future__ import annotations

import subprocess
from pathlib import Path

from gke_triage.models import TriageResult


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
        if f.manifest_path:
            lines.append(f"- Manifest: `{f.manifest_path}`")
        for e in f.evidence:
            lines.append(f"- {e}")
        lines.append("")

    if result.is_conclusive():
        lines += ["## Proposed fix", "",
                  "A patch is attached and (optionally) opened as a PR. "
                  "Review and merge via your normal GitOps flow.", ""]
    else:
        lines += ["## Inconclusive", "",
                  "No automated fix proposed. Ranked hypotheses above; "
                  "gather more evidence before acting.", ""]
    return "\n".join(lines)


def _open_pr(repo_root: Path, patch_path: Path, workload: str) -> str | None:
    branch = f"gke-triage/fix-{workload}"
    try:
        subprocess.run(["git", "-C", str(repo_root), "checkout", "-B", branch], check=True)
        subprocess.run(["git", "-C", str(repo_root), "apply", str(patch_path)], check=True)
        subprocess.run(["git", "-C", str(repo_root), "add", "-u"], check=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-m",
                        f"fix({workload}): gke-triage proposed fix"], check=True)
        subprocess.run(["git", "-C", str(repo_root), "push", "-u", "origin", branch], check=True)
        out = subprocess.run(
            ["gh", "pr", "create", "--fill", "--head", branch],
            cwd=str(repo_root), check=True, capture_output=True, text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_outputs(out_dir: str | Path, workload: str, namespace: str,
                  result: TriageResult, open_pr: bool = False,
                  repo_root: str | Path | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_name = f"{workload}-report.md"
    (out_dir / report_name).write_text(render_report(workload, namespace, result))

    patch_name = None
    pr_url = None
    if result.proposed_patch:
        patch_name = f"{workload}-fix.patch"
        patch_path = out_dir / patch_name
        patch_path.write_text(result.proposed_patch)
        if open_pr and repo_root:
            pr_url = _open_pr(Path(repo_root), patch_path, workload)

    return {"report": report_name, "patch": patch_name, "pr_url": pr_url}
