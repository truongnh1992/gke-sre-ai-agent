from gke_triage.models import ToolCall, Decision, Finding, TriageResult


def test_toolcall_roundtrip():
    tc = ToolCall(name="list_pods", args={"namespace": "prod"})
    assert tc.name == "list_pods"
    assert tc.args["namespace"] == "prod"


def test_decision_blocked_carries_reason():
    d = Decision(allowed=False, reason="mutating verb 'apply' blocked")
    assert d.allowed is False
    assert "apply" in d.reason


def test_finding_and_triageresult():
    f = Finding(
        summary="image tag typo",
        evidence=["pod payments-1 ImagePullBackOff", "manifest line 12: image: pay:latst"],
    )
    r = TriageResult(
        root_cause="image tag 'latst' does not exist",
        confidence="high",
        findings=[f],
    )
    assert r.confidence == "high"
    assert r.findings[0].summary == "image tag typo"
    assert r.is_conclusive()


def test_triageresult_inconclusive_when_low_confidence():
    r = TriageResult(root_cause="unclear", confidence="low", findings=[])
    assert not r.is_conclusive()
