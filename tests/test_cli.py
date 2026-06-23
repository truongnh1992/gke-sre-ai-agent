from typer.testing import CliRunner

from gke_triage.cli import app

runner = CliRunner()


def test_init_scaffolds_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    result = runner.invoke(app, ["init", "--path", str(cfg)])
    assert result.exit_code == 0
    assert cfg.exists()
    assert "gitops_repo" in cfg.read_text()


def test_diagnose_end_to_end_with_fake_runner(tmp_path, monkeypatch):
    repo = tmp_path / "gitops"
    (repo / "apps").mkdir(parents=True)
    (repo / "apps" / "payments.yaml").write_text(
        "kind: Deployment\nmetadata:\n  name: payments\n")

    sample = (
        'x```STRUCTURED_RESULT\n'
        '{"root_cause":"bad tag","confidence":"high",'
        '"findings":[{"summary":"ImagePullBackOff","evidence":["e1"],'
        '"manifest_path":"apps/payments.yaml"}],'
        '"proposed_patch":"--- a/apps/payments.yaml\\n+++ b/apps/payments.yaml\\n"}\n```'
    )
    monkeypatch.setattr("gke_triage.cli.gemini_runner", lambda prompt, workdir=None: sample)

    out_dir = tmp_path / "out"
    result = runner.invoke(app, [
        "diagnose", "payments", "-n", "prod",
        "--repo", str(repo), "--output", str(out_dir), "--no-pr",
    ])
    assert result.exit_code == 0, result.output
    assert (out_dir / "payments-report.md").exists()
    assert (out_dir / "payments-fix.patch").exists()
    assert "bad tag" in (out_dir / "payments-report.md").read_text()
