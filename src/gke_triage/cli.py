from __future__ import annotations

from pathlib import Path

import typer

from gke_triage.config import DEFAULT_CONFIG_YAML, DEFAULT_ENDPOINT, DEFAULT_AUDIT
from gke_triage.context.sources import find_manifest_for_workload
from gke_triage.engines import ensure_antigravity_setup, DEFAULT_MCP_CONFIG, DEFAULT_SKILLS_DIR
from gke_triage.orchestrator import diagnose as run_diagnose, get_runner
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
def register(
    config: str = typer.Option(DEFAULT_MCP_CONFIG, "--config", help="Antigravity MCP config path"),
    skills: str = typer.Option(DEFAULT_SKILLS_DIR, "--skills", help="Antigravity skills dir"),
    upstream: str = typer.Option(DEFAULT_ENDPOINT, "--upstream", help="Upstream GKE MCP endpoint"),
    audit: str = typer.Option(DEFAULT_AUDIT, "--audit", help="Audit log path"),
):
    """Register the read-only guardrail MCP server + skill with the Antigravity CLI."""
    info = ensure_antigravity_setup(upstream=upstream, audit_path=audit,
                                    config_path=config, skills_dir=skills)
    typer.echo(f"Registered '{info['server_name']}' in {info['config_path']}")
    typer.echo(f"Installed skill to {info['skill_path']}")


@app.command()
def diagnose(
    workload: str,
    namespace: str = typer.Option("default", "-n", "--namespace"),
    repo: str = typer.Option(".", "--repo", help="GitOps repo root"),
    output: str = typer.Option("./gke-triage-out", "--output"),
    open_pr: bool = typer.Option(True, "--pr/--no-pr"),
    engine: str = typer.Option("antigravity", "--engine", help="Reasoning engine: antigravity or gemini"),
):
    """Investigate a workload read-only and emit a report + proposed fix."""
    manifest_hint = find_manifest_for_workload(repo, workload)
    try:
        if engine == "antigravity":
            ensure_antigravity_setup(upstream=DEFAULT_ENDPOINT, audit_path=DEFAULT_AUDIT)
        runner = get_runner(engine)
        result = run_diagnose(workload, namespace, runner=runner,
                              workdir=Path(repo), manifest_hint=manifest_hint)
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
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
