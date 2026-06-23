import pytest

from gke_triage.models import TriageResult
from gke_triage.orchestrator import parse_structured_result, diagnose


SAMPLE = '''
Some chatter from the agent...
```STRUCTURED_RESULT
{"root_cause": "bad tag", "confidence": "high",
 "findings": [{"summary": "ImagePullBackOff", "evidence": ["e1"], "manifest_path": "d.yaml"}],
 "proposed_patch": "--- a/d.yaml\\n+++ b/d.yaml\\n"}
```
trailing text
'''


def test_parse_structured_result_extracts_block():
    r = parse_structured_result(SAMPLE)
    assert isinstance(r, TriageResult)
    assert r.root_cause == "bad tag"
    assert r.confidence == "high"
    assert r.findings[0].manifest_path == "d.yaml"
    assert r.proposed_patch.startswith("--- a/d.yaml")


def test_parse_missing_block_returns_inconclusive():
    r = parse_structured_result("no block here")
    assert r.confidence == "low"
    assert r.proposed_patch is None


def test_diagnose_uses_injected_runner(tmp_path):
    def fake_runner(prompt: str, workdir) -> str:
        assert "payments" in prompt
        return SAMPLE
    r = diagnose("payments", "prod", runner=fake_runner)
    assert r.root_cause == "bad tag"
