import os
from pathlib import Path

from gke_triage.orchestrator import gemini_runner


def test_gemini_runner_invokes_command_and_returns_stdout(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env_has_skill"] = "GEMINI_SKILLS_DIR" in kwargs.get("env", {})
        class R:
            stdout = "STRUCTURED_RESULT output"
            returncode = 0
        return R()

    monkeypatch.setattr("gke_triage.orchestrator.subprocess.run", fake_run)
    out = gemini_runner("investigate payments", workdir=tmp_path)
    assert out == "STRUCTURED_RESULT output"
    assert captured["cmd"][0] == "gemini"
    assert "-p" in captured["cmd"]
