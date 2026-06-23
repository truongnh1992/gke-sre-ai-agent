import os
from pathlib import Path

from gke_scout.orchestrator import gemini_runner


def test_gemini_runner_raises_on_nonzero_exit(tmp_path, monkeypatch):
    import pytest
    def fake_run(cmd, **kwargs):
        class R:
            stdout = ""
            stderr = "auth failed"
            returncode = 1
        return R()
    monkeypatch.setattr("gke_scout.orchestrator.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="auth failed"):
        gemini_runner("x", workdir=tmp_path)


def test_gemini_runner_invokes_command_and_returns_stdout(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env_has_skill"] = "GEMINI_SKILLS_DIR" in kwargs.get("env", {})
        class R:
            stdout = "STRUCTURED_RESULT output"
            returncode = 0
        return R()

    monkeypatch.setattr("gke_scout.orchestrator.subprocess.run", fake_run)
    out = gemini_runner("investigate payments", workdir=tmp_path)
    assert out == "STRUCTURED_RESULT output"
    assert captured["cmd"][0] == "gemini"
    assert "-p" in captured["cmd"]
