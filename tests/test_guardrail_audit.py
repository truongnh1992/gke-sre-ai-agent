import json

from gke_triage.guardrail.audit import AuditLog
from gke_triage.models import Decision, ToolCall


def test_appends_jsonl_entries(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.record(ToolCall("list_pods", {"namespace": "prod"}),
               Decision(allowed=True, reason="ok"))
    log.record(ToolCall("delete_pod", {"name": "x"}),
               Decision(allowed=False, reason="blocked"))

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["tool"] == "list_pods"
    assert first["allowed"] is True
    assert first["args"] == {"namespace": "prod"}
    second = json.loads(lines[1])
    assert second["allowed"] is False
    assert second["reason"] == "blocked"
    assert "ts" in first


def test_append_only_across_instances(tmp_path):
    path = tmp_path / "audit.jsonl"
    AuditLog(path).record(ToolCall("get_pod", {}), Decision(True))
    AuditLog(path).record(ToolCall("get_pod", {}), Decision(True))
    assert len(path.read_text().strip().splitlines()) == 2
