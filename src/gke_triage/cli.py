from __future__ import annotations

from pathlib import Path

import typer

from gke_triage.config import DEFAULT_CONFIG_YAML
from gke_triage.orchestrator import diagnose as run_diagnose, gemini_runner
from gke_triage.reporter import write_outputs

app = typer.Typer(help="Local AI on-call SRE for GKE (read-only triage + GitOps fix PRs).")


@app.command()
def init(path: str = typer.Option("~/.gke-triage/config.yaml", "--path")):
    """Scaffold a config file."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(DEFAULT_CONFIG_YAML)
    typer.echo(f"Wrote config template to {p}")


@app.command()
def diagnose(
    workload: str,
    namespace: str = typer.Option("default", "-n", "--namespace"),
    repo: str = typer.Option(".", "--repo", help="GitOps repo root"),
    output: str = typer.Option("./gke-triage-out", "--output"),
    open_pr: bool = typer.Option(True, "--pr/--no-pr"),
):
    """Investigate a workload read-only and emit a report + proposed fix."""
    result = run_diagnose(workload, namespace, runner=gemini_runner)
    out = write_outputs(output, workload, namespace, result,
                        open_pr=open_pr, repo_root=repo)
    typer.echo(f"Report: {Path(output) / out['report']}")
    if out["patch"]:
        typer.echo(f"Patch:  {Path(output) / out['patch']}")
    if out["pr_url"]:
        typer.echo(f"PR:     {out['pr_url']}")
    if not result.is_conclusive():
        typer.echo("Result inconclusive — see ranked hypotheses in the report.")


@app.command(name="_serve-proxy", hidden=True)
def serve_proxy():
    """Run the guardrail stdio MCP server (invoked by Gemini CLI)."""
    from gke_triage.guardrail.server import main
    main()


if __name__ == "__main__":
    app()
