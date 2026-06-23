import asyncio
from dataclasses import dataclass

import pytest

from gke_triage.guardrail.audit import AuditLog
from gke_triage.guardrail.server import handle_call_tool


@dataclass
class FakeResult:
    data: dict

    def model_dump(self):
        return self.data


class FakeSession:
    """Minimal stand-in for an MCP ClientSession."""

    def __init__(self, result=None, *, delay: float = 0, error: Exception | None = None):
        self._result = result
        self._delay = delay
        self._error = error

    async def call_tool(self, name, args):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._result


def test_allowed_call_returns_redacted_result(tmp_path):
    session = FakeSession(FakeResult({"content": [{"type": "text", "text": "password: secret123"}]}))
    audit = AuditLog(tmp_path / "a.jsonl")
    result = asyncio.run(handle_call_tool("list_pods", {}, session=session, audit=audit))
    assert len(result.content) == 1
    assert "REDACTED" in result.content[0].text


def test_blocked_call_returns_refused(tmp_path):
    session = FakeSession(FakeResult({"ok": True}))
    audit = AuditLog(tmp_path / "a.jsonl")
    result = asyncio.run(handle_call_tool("delete_pod", {"name": "p"}, session=session, audit=audit))
    assert len(result.content) == 1
    assert "Refused" in result.content[0].text


def test_upstream_timeout_returns_error(tmp_path):
    session = FakeSession(delay=5)
    audit = AuditLog(tmp_path / "a.jsonl")
    result = asyncio.run(handle_call_tool("list_pods", {}, session=session, audit=audit,
                                          call_timeout=0.01))
    assert len(result.content) == 1
    assert "timed out" in result.content[0].text
    assert "list_pods" in result.content[0].text


def test_upstream_exception_fails_closed(tmp_path):
    session = FakeSession(error=RuntimeError("db password leaked"))
    audit = AuditLog(tmp_path / "a.jsonl")
    result = asyncio.run(handle_call_tool("list_pods", {}, session=session, audit=audit))
    assert len(result.content) == 1
    assert "failed safely" in result.content[0].text
    assert "leaked" not in result.content[0].text


def test_upstream_base_exception_group_fails_closed(tmp_path):
    """BaseExceptionGroup (from anyio task groups) must not crash the proxy."""
    inner = RuntimeError("401 Unauthorized")
    session = FakeSession(error=BaseExceptionGroup("unhandled", [inner]))
    audit = AuditLog(tmp_path / "a.jsonl")
    result = asyncio.run(handle_call_tool("get_k8s_resource", {"parent": "x"}, session=session, audit=audit))
    assert len(result.content) == 1
    assert "failed safely" in result.content[0].text
    assert "401" not in result.content[0].text
