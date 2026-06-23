import subprocess

import pytest

from gke_triage.models import TriageResult
from gke_triage.orchestrator import (
    DEFAULT_TIMEOUT, EngineTimeout, parse_structured_result, diagnose, _run_cli,
)


SAMPLE = '''
Some chatter from the agent...
```STRUCTURED_RESULT
{"root_cause": "bad tag", "confidence": "high",
 "findings": [{"summary": "ImagePullBackOff", "evidence": ["e1"]}]}
```
trailing text
'''


def test_parse_structured_result_extracts_block():
    r = parse_structured_result(SAMPLE)
    assert isinstance(r, TriageResult)
    assert r.root_cause == "bad tag"
    assert r.confidence == "high"
    assert r.findings[0].summary == "ImagePullBackOff"
    assert r.findings[0].evidence == ["e1"]


def test_parse_missing_block_returns_inconclusive():
    r = parse_structured_result("no block here")
    assert r.confidence == "low"
    assert not r.is_conclusive()


def test_diagnose_calls_engine(tmp_path, monkeypatch):
    from gke_triage import orchestrator
    calls = []
    def fake_runner(prompt: str, workdir=None, timeout=None) -> str:
        calls.append(prompt)
        return SAMPLE
    monkeypatch.setattr(orchestrator, "ENGINES",
                        {"fake": (fake_runner, False)})
    r = diagnose("payments", "prod", engine="fake")
    assert r.root_cause == "bad tag"
    assert "payments" in calls[0]


def test_diagnose_forwards_timeout(monkeypatch):
    from gke_triage import orchestrator
    captured = {}
    def fake_runner(prompt: str, workdir=None, timeout=None) -> str:
        captured["timeout"] = timeout
        return SAMPLE
    monkeypatch.setattr(orchestrator, "ENGINES",
                        {"fake": (fake_runner, False)})
    diagnose("svc", "ns", engine="fake", timeout=42)
    assert captured["timeout"] == 42


def test_run_cli_timeout_raises(monkeypatch):
    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 5))
    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(EngineTimeout, match="timed out after 5s"):
        _run_cli(["fake"], None, {}, "Test", "fake-cli", timeout=5)


def test_run_cli_timeout_captures_partial_output(monkeypatch):
    def mock_run(*args, **kwargs):
        exc = subprocess.TimeoutExpired(cmd=args[0], timeout=5)
        exc.stdout = b"partial agent output here"
        exc.stderr = b"some stderr"
        raise exc
    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(EngineTimeout) as exc_info:
        _run_cli(["fake"], None, {}, "Test", "fake-cli", timeout=5)
    assert exc_info.value.partial_stdout == "partial agent output here"
    assert exc_info.value.partial_stderr == "some stderr"


def test_get_engine_selects_engines():
    from gke_triage.orchestrator import get_engine, antigravity_runner, gemini_runner
    runner_agy, inline_agy = get_engine("antigravity")
    runner_gem, inline_gem = get_engine("gemini")
    assert runner_agy is antigravity_runner
    assert runner_gem is gemini_runner
    assert inline_agy is True
    assert inline_gem is False


def test_get_engine_unknown_raises():
    from gke_triage.orchestrator import get_engine
    with pytest.raises(ValueError, match="unknown engine"):
        get_engine("bogus")
