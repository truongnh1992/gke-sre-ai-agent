from __future__ import annotations

from pathlib import Path

import typer

from gke_triage.config import DEFAULT_CONFIG_YAML, DEFAULT_ENDPOINT, DEFAULT_AUDIT
from gke_triage.engines import ensure_antigravity_setup, DEFAULT_MCP_CONFIG, DEFAULT_SKILLS_DIR
from gke_triage.orchestrator import DEFAULT_TIMEOUT, diagnose as run_diagnose
from gke_triage.reporter import write_outputs

app = typer.Typer(help="Local AI on-call SRE for GKE (read-only triage with evidence-cited reports).")


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
    output: str = typer.Option("./gke-triage-out", "--output"),
    engine: str = typer.Option("antigravity", "--engine", help="Reasoning engine: antigravity or gemini"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print raw engine output for debugging"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", "-t", help="Max seconds to wait for the agent (0 = no limit)"),
):
    """Investigate a workload read-only and emit an evidence-cited report."""
    try:
        if engine == "antigravity":
            ensure_antigravity_setup(upstream=DEFAULT_ENDPOINT, audit_path=DEFAULT_AUDIT)
        effective_timeout = timeout if timeout > 0 else None
        result = run_diagnose(workload, namespace, engine=engine, verbose=verbose,
                              timeout=effective_timeout)
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
    out = write_outputs(output, workload, namespace, result)
    typer.echo(f"Report: {Path(output) / out['report']}")
    if not result.is_conclusive():
        typer.echo("Result inconclusive — see ranked hypotheses in the report.")


@app.command(name="_serve-proxy", hidden=True)
def serve_proxy():
    """Run the guardrail stdio MCP server (invoked by Gemini CLI)."""
    from gke_triage.guardrail.server import main
    main()


if __name__ == "__main__":
    app()
