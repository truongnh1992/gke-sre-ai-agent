from typer.testing import CliRunner

from gke_triage.cli import app

runner = CliRunner()


def test_init_scaffolds_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    result = runner.invoke(app, ["init", "--path", str(cfg)])
    assert result.exit_code == 0
    assert cfg.exists()
    assert "upstream_mcp_endpoint" in cfg.read_text()


def test_diagnose_end_to_end_with_fake_runner(tmp_path, monkeypatch):
    from gke_triage import orchestrator

    sample = (
        'x```STRUCTURED_RESULT\n'
        '{"root_cause":"bad tag","confidence":"high",'
        '"findings":[{"summary":"ImagePullBackOff","evidence":["e1"]}]}\n```'
    )
    fake_runner = lambda prompt, workdir=None, timeout=None: sample
    monkeypatch.setattr(orchestrator, "ENGINES",
                        {"antigravity": (fake_runner, True)})
    monkeypatch.setattr("gke_triage.cli.ensure_antigravity_setup", lambda **kw: {"config_path": "x", "skill_path": "y", "server_name": "z"})

    out_dir = tmp_path / "out"
    result = runner.invoke(app, [
        "diagnose", "payments", "-n", "prod", "--output", str(out_dir),
    ])
    assert result.exit_code == 0, result.output
    report = out_dir / "payments-report.md"
    assert report.exists()
    assert "bad tag" in report.read_text()
    assert not (out_dir / "payments-fix.patch").exists()


def test_register_command_writes_config_and_skill(tmp_path, monkeypatch):
    import json
    import gke_triage.engines as eng
    monkeypatch.setattr(eng, "DEFAULT_ISOLATED_MCP_CONFIG",
                        str(tmp_path / "isolated_mcp.json"))
    cfg = tmp_path / "mcp_config.json"
    skills = tmp_path / "skills"
    result = runner.invoke(app, ["register", "--config", str(cfg), "--skills", str(skills)])
    assert result.exit_code == 0, result.output
    data = json.loads(cfg.read_text())
    assert "gke-triage-guardrail" in data["mcpServers"]
    assert (skills / "k8s-troubleshooter" / "SKILL.md").exists()


def test_diagnose_registers_guardrail_for_antigravity(tmp_path, monkeypatch):
    from gke_triage import orchestrator

    called = {}
    monkeypatch.setattr("gke_triage.cli.ensure_antigravity_setup",
                        lambda **kw: called.setdefault("kw", kw) or {"config_path": "x", "skill_path": "y", "server_name": "z"})
    fake_runner = lambda prompt, workdir=None, timeout=None: "no structured block"
    monkeypatch.setattr(orchestrator, "ENGINES",
                        {"antigravity": (fake_runner, True)})
    result = runner.invoke(app, ["diagnose", "x", "-n", "prod",
                                 "--output", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "kw" in called
