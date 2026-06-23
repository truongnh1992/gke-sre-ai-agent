import pytest

from gke_triage.orchestrator import antigravity_runner


def _patch_config_swap(monkeypatch, tmp_path):
    """Prevent antigravity_runner from touching the real MCP config."""
    iso_cfg = tmp_path / "isolated_mcp.json"
    shared_cfg = tmp_path / "shared_mcp.json"
    shared_cfg.write_text('{"mcpServers":{}}')
    monkeypatch.setattr("gke_triage.engines.DEFAULT_ISOLATED_MCP_CONFIG",
                        str(iso_cfg))
    monkeypatch.setattr("gke_triage.engines.DEFAULT_MCP_CONFIG",
                        str(shared_cfg))
    from gke_triage import orchestrator
    monkeypatch.setattr(orchestrator, "_AGY_CONVERSATIONS_DIR",
                        tmp_path / "conversations")


def test_antigravity_runner_invokes_agy_and_returns_stdout(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R:
            stdout = "STRUCTURED_RESULT output"
            stderr = ""
            returncode = 0
        return R()

    _patch_config_swap(monkeypatch, tmp_path)
    monkeypatch.setattr("gke_triage.orchestrator.subprocess.run", fake_run)
    out = antigravity_runner("investigate payments", workdir=tmp_path)
    assert out == "STRUCTURED_RESULT output"
    assert captured["cmd"][0] == "agy"
    assert "-p" in captured["cmd"]


def test_antigravity_runner_raises_on_nonzero_exit(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            stdout = ""
            stderr = "auth failed"
            returncode = 1
        return R()

    _patch_config_swap(monkeypatch, tmp_path)
    monkeypatch.setattr("gke_triage.orchestrator.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="auth failed"):
        antigravity_runner("x", workdir=tmp_path)


def test_antigravity_runner_raises_on_empty_output(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            stdout = ""
            stderr = ""
            returncode = 0
        return R()

    _patch_config_swap(monkeypatch, tmp_path)
    monkeypatch.setattr("gke_triage.orchestrator.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="no output"):
        antigravity_runner("x", workdir=tmp_path)
