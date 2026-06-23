import json

from gke_scout.guardrail.proxy import Guardrail
from gke_scout.guardrail.audit import AuditLog
from gke_scout.models import ToolCall


class FakeUpstream:
    def __init__(self, result):
        self.result = result
        self.called_with = None

    def call(self, call: ToolCall):
        self.called_with = call
        return self.result


def test_blocked_call_not_forwarded(tmp_path):
    upstream = FakeUpstream({"data": "x"})
    g = Guardrail(upstream=upstream, audit=AuditLog(tmp_path / "a.jsonl"))
    out = g.enforce(ToolCall("delete_pod", {"name": "p"}))
    assert upstream.called_with is None
    assert out["error"]
    assert "blocked" in out["error"].lower()


def test_allowed_call_forwarded_and_redacted(tmp_path):
    upstream = FakeUpstream({"kind": "Secret", "data": {"password": "c2VjcmV0"}})
    g = Guardrail(upstream=upstream, audit=AuditLog(tmp_path / "a.jsonl"))
    out = g.enforce(ToolCall("get_secret", {"name": "db"}))
    assert upstream.called_with.name == "get_secret"
    assert out["data"]["password"] == "***REDACTED***"


def test_every_call_audited(tmp_path):
    path = tmp_path / "a.jsonl"
    upstream = FakeUpstream({"ok": True})
    g = Guardrail(upstream=upstream, audit=AuditLog(path))
    g.enforce(ToolCall("list_pods", {}))
    g.enforce(ToolCall("delete_pod", {}))
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["allowed"] is True
    assert json.loads(lines[1])["allowed"] is False


def test_upstream_exception_fails_closed(tmp_path):
    class Boom:
        def call(self, call):
            raise RuntimeError("db secret leaked in message")
    g = Guardrail(upstream=Boom(), audit=AuditLog(tmp_path / "a.jsonl"))
    out = g.enforce(ToolCall("list_pods", {}))
    assert "error" in out
    assert "leaked" not in str(out)  # exception message must not surface
