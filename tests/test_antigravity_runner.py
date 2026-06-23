import pytest

from gke_triage.orchestrator import antigravity_runner


def test_antigravity_runner_invokes_agy_and_returns_stdout(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R:
            stdout = "STRUCTURED_RESULT output"
            stderr = ""
            returncode = 0
        return R()

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

    monkeypatch.setattr("gke_triage.orchestrator.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="auth failed"):
        antigravity_runner("x", workdir=tmp_path)
