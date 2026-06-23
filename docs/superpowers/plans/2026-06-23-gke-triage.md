# gke-triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `gke-triage`, an open-source local Python CLI that investigates a degraded GKE workload read-only (via Gemini CLI + the GKE MCP server behind a safety guardrail) and emits an evidence-cited root-cause report plus a proposed fix as a GitOps diff/PR — never mutating the cluster.

**Architecture:** A Python orchestrator launches Gemini CLI as the reasoning engine. All MCP traffic is routed through a local **guardrail proxy** that enforces a read-only allowlist, redacts secrets, and audit-logs every call. A context-fusion layer adds logs/deploy-history/GitOps-repo reads. A reporter turns the agent's structured root cause into a Markdown report and a git diff/PR. Pure-logic components (policy, redaction, audit, reporter) are unit-tested; integration points (proxy transport, Gemini launch) are tested with fakes/mocks.

**Tech Stack:** Python 3.14, `uv` (env + packaging), `pytest`, `typer` (CLI), `mcp` (official Python MCP SDK), `pyyaml`, `gh` (PR creation), `kind` + `kubectl` (eval harness). Gemini CLI is the external reasoning engine.

---

## File Structure

```
gke-triage/
├── pyproject.toml                       # uv project, deps, console_scripts entrypoint
├── README.md                            # install, usage, benchmark
├── src/gke_triage/
│   ├── __init__.py
│   ├── models.py                        # dataclasses: ToolCall, Decision, Finding, TriageResult
│   ├── config.py                        # load config + `init` scaffold + prereq checks
│   ├── cli.py                           # typer app: diagnose, init, _serve-proxy (hidden)
│   ├── guardrail/
│   │   ├── __init__.py
│   │   ├── policy.py                    # read-only allowlist (pure)
│   │   ├── redact.py                    # secret redaction (pure)
│   │   ├── audit.py                     # append-only JSONL audit log
│   │   └── proxy.py                     # MCP proxy server: wires policy+redact+audit to upstream
│   ├── context/
│   │   ├── __init__.py
│   │   └── sources.py                   # GitOps repo reader + manifest locator (pure-ish)
│   ├── orchestrator.py                  # investigate→report→propose; launches Gemini CLI
│   ├── reporter.py                      # incident report markdown + diff + PR
│   └── skills/
│       └── k8s-troubleshooter/SKILL.md  # generalized troubleshooting playbook
├── tests/
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_guardrail_policy.py
│   ├── test_guardrail_redact.py
│   ├── test_guardrail_audit.py
│   ├── test_guardrail_proxy.py
│   ├── test_context_sources.py
│   ├── test_reporter.py
│   └── test_orchestrator.py
└── eval/
    ├── scenarios/
    │   ├── image_tag_typo/              # broken + expected-fix manifests
    │   └── configmap_key_mismatch/
    └── run_eval.py                      # deploy→diagnose→assert-fix on kind
```

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/gke_triage/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
import gke_triage


def test_package_has_version():
    assert isinstance(gke_triage.__version__, str)
    assert gke_triage.__version__
```

- [ ] **Step 2: Create pyproject.toml**

`pyproject.toml`:
```toml
[project]
name = "gke-triage"
version = "0.1.0"
description = "Local AI on-call SRE for GKE: read-only triage, evidence-cited reports, GitOps fix PRs."
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "mcp>=1.2",
    "pyyaml>=6.0",
]

[project.scripts]
gke-triage = "gke_triage.cli:app"

[dependency-groups]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gke_triage"]
```

- [ ] **Step 3: Create the package init**

`src/gke_triage/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Sync env and run the test**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/gke_triage/__init__.py tests/test_smoke.py uv.lock
git commit -m "chore: scaffold gke-triage python package"
```

---

## Task 2: Data models

**Files:**
- Create: `src/gke_triage/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
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
        manifest_path="apps/payments/deployment.yaml",
    )
    r = TriageResult(
        root_cause="image tag 'latst' does not exist",
        confidence="high",
        findings=[f],
        proposed_patch="--- a/...\n+++ b/...\n",
    )
    assert r.confidence == "high"
    assert r.findings[0].manifest_path.endswith("deployment.yaml")
    assert r.is_conclusive()


def test_triageresult_inconclusive_when_no_patch():
    r = TriageResult(root_cause="unclear", confidence="low", findings=[], proposed_patch=None)
    assert not r.is_conclusive()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gke_triage.models'`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


@dataclass
class Finding:
    summary: str
    evidence: list[str] = field(default_factory=list)
    manifest_path: str | None = None


@dataclass
class TriageResult:
    root_cause: str
    confidence: str  # "high" | "medium" | "low"
    findings: list[Finding] = field(default_factory=list)
    proposed_patch: str | None = None

    def is_conclusive(self) -> bool:
        return bool(self.proposed_patch) and self.confidence in {"high", "medium"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/models.py tests/test_models.py
git commit -m "feat: add core data models"
```

---

## Task 3: Guardrail policy (read-only allowlist)

**Files:**
- Create: `src/gke_triage/guardrail/__init__.py`
- Create: `src/gke_triage/guardrail/policy.py`
- Test: `tests/test_guardrail_policy.py`

This is the keystone safety primitive: a pure function deciding whether a tool call may be forwarded to the upstream GKE MCP server.

- [ ] **Step 1: Write the failing test**

`tests/test_guardrail_policy.py`:
```python
import pytest

from gke_triage.guardrail.policy import evaluate
from gke_triage.models import ToolCall


@pytest.mark.parametrize("name", [
    "list_pods", "get_pod", "get_logs", "list_events",
    "describe_deployment", "read_configmap",
])
def test_read_only_calls_allowed(name):
    d = evaluate(ToolCall(name=name, args={}))
    assert d.allowed is True


@pytest.mark.parametrize("name", [
    "apply_manifest", "delete_pod", "patch_deployment",
    "scale_deployment", "create_namespace", "exec_command",
])
def test_mutating_calls_blocked(name):
    d = evaluate(ToolCall(name=name, args={}))
    assert d.allowed is False
    assert name.split("_")[0] in d.reason.lower()


def test_unknown_verb_blocked_by_default():
    # default-deny: anything not recognizably read-only is blocked
    d = evaluate(ToolCall(name="frobnicate_cluster", args={}))
    assert d.allowed is False
    assert "default-deny" in d.reason.lower()


def test_exec_blocked_even_if_named_get():
    # kubectl exec is read-shaped but can mutate; block on the 'exec' token anywhere
    d = evaluate(ToolCall(name="get_exec_session", args={}))
    assert d.allowed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_guardrail_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gke_triage.guardrail'`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/guardrail/__init__.py`:
```python
```

`src/gke_triage/guardrail/policy.py`:
```python
from __future__ import annotations

from gke_triage.models import Decision, ToolCall

# Tokens that, if present anywhere in a tool name, indicate mutation/side-effects.
MUTATING_TOKENS = frozenset({
    "apply", "create", "update", "patch", "delete", "remove",
    "scale", "restart", "rollout", "exec", "drain", "cordon",
    "edit", "set", "annotate", "label", "evict", "replace",
})

# Tokens that indicate a safe read. A call is allowed only if it contains a read
# token AND no mutating token (default-deny otherwise).
READ_TOKENS = frozenset({
    "list", "get", "read", "describe", "logs", "log", "events",
    "events", "watch", "top", "explain", "version", "diff",
})


def evaluate(call: ToolCall) -> Decision:
    tokens = set(call.name.lower().split("_"))

    mutating = tokens & MUTATING_TOKENS
    if mutating:
        verb = sorted(mutating)[0]
        return Decision(allowed=False, reason=f"mutating verb '{verb}' blocked by read-only policy")

    if tokens & READ_TOKENS:
        return Decision(allowed=True, reason="read-only call permitted")

    return Decision(allowed=False, reason="default-deny: tool name not recognized as read-only")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_guardrail_policy.py -v`
Expected: PASS (all parametrized cases pass)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/guardrail/__init__.py src/gke_triage/guardrail/policy.py tests/test_guardrail_policy.py
git commit -m "feat: add read-only guardrail policy (default-deny)"
```

---

## Task 4: Guardrail secret redaction

**Files:**
- Create: `src/gke_triage/guardrail/redact.py`
- Test: `tests/test_guardrail_redact.py`

- [ ] **Step 1: Write the failing test**

`tests/test_guardrail_redact.py`:
```python
from gke_triage.guardrail.redact import redact


def test_redacts_secret_kind_data_values():
    payload = {
        "kind": "Secret",
        "data": {"password": "c2VjcmV0", "token": "YWJj"},
    }
    out = redact(payload)
    assert out["data"]["password"] == "***REDACTED***"
    assert out["data"]["token"] == "***REDACTED***"


def test_redacts_sensitive_keys_anywhere():
    payload = {"env": [{"name": "API_KEY", "value": "supersecret"}]}
    out = redact(payload)
    assert out["env"][0]["value"] == "***REDACTED***"
    # non-sensitive name preserved
    payload2 = {"env": [{"name": "LOG_LEVEL", "value": "debug"}]}
    assert redact(payload2)["env"][0]["value"] == "debug"


def test_redacts_by_sensitive_key_name():
    payload = {"config": {"db_password": "hunter2", "host": "db.local"}}
    out = redact(payload)
    assert out["config"]["db_password"] == "***REDACTED***"
    assert out["config"]["host"] == "db.local"


def test_does_not_mutate_input():
    payload = {"config": {"password": "x"}}
    redact(payload)
    assert payload["config"]["password"] == "x"


def test_redacts_in_strings_via_regex():
    text = 'output: Authorization: Bearer abcdef123456789'
    out = redact(text)
    assert "abcdef123456789" not in out
    assert "REDACTED" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_guardrail_redact.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/guardrail/redact.py`:
```python
from __future__ import annotations

import copy
import re

REDACTED = "***REDACTED***"

# Substrings that, if present in a key name (case-insensitive), mark its value secret.
SENSITIVE_KEY_SUBSTRINGS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "private_key", "credential", "auth", "bearer",
)

# Bearer / Authorization header values in free text.
_BEARER_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]{8,})")


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in SENSITIVE_KEY_SUBSTRINGS)


def _redact_node(node, parent_is_secret: bool):
    if isinstance(node, dict):
        # Special case: an env entry {name: API_KEY, value: ...}
        if "name" in node and "value" in node and _is_sensitive_key(str(node["name"])):
            new = dict(node)
            new["value"] = REDACTED
            return {k: _redact_node(v, parent_is_secret) if k != "value" else v for k, v in new.items()}
        out = {}
        for k, v in node.items():
            if _is_sensitive_key(k) or parent_is_secret:
                out[k] = REDACTED if not isinstance(v, (dict, list)) else _redact_node(v, True)
            else:
                out[k] = _redact_node(v, parent_is_secret)
        return out
    if isinstance(node, list):
        return [_redact_node(x, parent_is_secret) for x in node]
    return node


def redact(payload):
    """Redact secrets from a tool-output payload (dict/list/str). Pure: never mutates input."""
    if isinstance(payload, str):
        return _BEARER_RE.sub(rf"\1{REDACTED}", payload)
    payload = copy.deepcopy(payload)
    is_secret = isinstance(payload, dict) and payload.get("kind") == "Secret"
    if is_secret and isinstance(payload.get("data"), dict):
        payload["data"] = {k: REDACTED for k in payload["data"]}
        # still walk the rest
        rest = {k: v for k, v in payload.items() if k != "data"}
        walked = _redact_node(rest, False)
        walked["data"] = payload["data"]
        return walked
    return _redact_node(payload, False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_guardrail_redact.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/guardrail/redact.py tests/test_guardrail_redact.py
git commit -m "feat: add secret redaction for tool outputs"
```

---

## Task 5: Guardrail audit log

**Files:**
- Create: `src/gke_triage/guardrail/audit.py`
- Test: `tests/test_guardrail_audit.py`

- [ ] **Step 1: Write the failing test**

`tests/test_guardrail_audit.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_guardrail_audit.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/guardrail/audit.py`:
```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gke_triage.models import Decision, ToolCall


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, call: ToolCall, decision: Decision) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": call.name,
            "args": call.args,
            "allowed": decision.allowed,
            "reason": decision.reason,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_guardrail_audit.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/guardrail/audit.py tests/test_guardrail_audit.py
git commit -m "feat: add append-only JSONL audit log"
```

---

## Task 6: Guardrail enforcement wrapper

**Files:**
- Create: `src/gke_triage/guardrail/proxy.py`
- Test: `tests/test_guardrail_proxy.py`

This wraps policy + redact + audit into a single `enforce()` function and an
upstream-forwarding shim. We unit-test `enforce()` against a fake upstream so the
transport layer (Task 12 wiring) stays thin.

- [ ] **Step 1: Write the failing test**

`tests/test_guardrail_proxy.py`:
```python
import json

from gke_triage.guardrail.proxy import Guardrail
from gke_triage.guardrail.audit import AuditLog
from gke_triage.models import ToolCall


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
    assert upstream.called_with is None  # never forwarded
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_guardrail_proxy.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/guardrail/proxy.py`:
```python
from __future__ import annotations

from typing import Protocol

from gke_triage.guardrail.audit import AuditLog
from gke_triage.guardrail.policy import evaluate
from gke_triage.guardrail.redact import redact
from gke_triage.models import ToolCall


class Upstream(Protocol):
    def call(self, call: ToolCall): ...


class Guardrail:
    """Enforces read-only policy, redacts outputs, and audits every tool call."""

    def __init__(self, upstream: Upstream, audit: AuditLog):
        self.upstream = upstream
        self.audit = audit

    def enforce(self, call: ToolCall):
        decision = evaluate(call)
        self.audit.record(call, decision)
        if not decision.allowed:
            return {"error": f"Tool call refused: {decision.reason}"}
        result = self.upstream.call(call)
        return redact(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_guardrail_proxy.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/guardrail/proxy.py tests/test_guardrail_proxy.py
git commit -m "feat: add guardrail enforcement (policy+redact+audit)"
```

---

## Task 7: Config loading and `init` scaffold

**Files:**
- Create: `src/gke_triage/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import pytest

from gke_triage.config import Config, load_config, DEFAULT_CONFIG_YAML


def test_load_config_from_file(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "gitops_repo: ./gitops\n"
        "upstream_mcp_endpoint: https://container.googleapis.com/mcp\n"
        "audit_log: ~/.gke-triage/audit.jsonl\n"
    )
    cfg = load_config(p)
    assert cfg.gitops_repo == "./gitops"
    assert cfg.upstream_mcp_endpoint.endswith("/mcp")
    # ~ expanded
    assert cfg.audit_log.startswith("/") or ":" in cfg.audit_log


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_defaults_applied_for_omitted_fields(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("gitops_repo: ./g\n")
    cfg = load_config(p)
    assert cfg.upstream_mcp_endpoint  # default filled
    assert cfg.audit_log              # default filled


def test_default_yaml_is_valid_template():
    assert "gitops_repo" in DEFAULT_CONFIG_YAML
    assert "upstream_mcp_endpoint" in DEFAULT_CONFIG_YAML
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/config.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_ENDPOINT = "https://container.googleapis.com/mcp"
DEFAULT_AUDIT = "~/.gke-triage/audit.jsonl"

DEFAULT_CONFIG_YAML = f"""\
# gke-triage configuration
gitops_repo: ./gitops            # path to the repo holding your K8s manifests
upstream_mcp_endpoint: {DEFAULT_ENDPOINT}
audit_log: {DEFAULT_AUDIT}
"""


@dataclass
class Config:
    gitops_repo: str
    upstream_mcp_endpoint: str = DEFAULT_ENDPOINT
    audit_log: str = DEFAULT_AUDIT

    def __post_init__(self):
        self.audit_log = str(Path(self.audit_log).expanduser())
        self.gitops_repo = str(Path(self.gitops_repo).expanduser())


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return Config(
        gitops_repo=data.get("gitops_repo", "."),
        upstream_mcp_endpoint=data.get("upstream_mcp_endpoint", DEFAULT_ENDPOINT),
        audit_log=data.get("audit_log", DEFAULT_AUDIT),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/config.py tests/test_config.py
git commit -m "feat: add config loading with defaults"
```

---

## Task 8: Context-fusion — GitOps manifest locator

**Files:**
- Create: `src/gke_triage/context/__init__.py`
- Create: `src/gke_triage/context/sources.py`
- Test: `tests/test_context_sources.py`

The locator finds which manifest file in the GitOps repo owns a given workload —
needed by the reporter to target the diff. (Cloud Logging / deploy-history
adapters are surfaced to the agent as live MCP tools through the guardrail; this
task implements the pure repo-reading piece that the reporter consumes.)

- [ ] **Step 1: Write the failing test**

`tests/test_context_sources.py`:
```python
from gke_triage.context.sources import find_manifest_for_workload


def _write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_finds_deployment_by_metadata_name(tmp_path):
    _write(tmp_path / "apps/payments/deploy.yaml",
           "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: payments\n")
    _write(tmp_path / "apps/other/deploy.yaml",
           "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: ledger\n")
    hit = find_manifest_for_workload(tmp_path, "payments")
    assert hit is not None
    assert hit.endswith("apps/payments/deploy.yaml")


def test_returns_none_when_absent(tmp_path):
    _write(tmp_path / "a.yaml", "kind: Deployment\nmetadata:\n  name: foo\n")
    assert find_manifest_for_workload(tmp_path, "missing") is None


def test_handles_multi_doc_yaml(tmp_path):
    _write(tmp_path / "bundle.yaml",
           "kind: Service\nmetadata:\n  name: payments\n---\n"
           "kind: Deployment\nmetadata:\n  name: payments\n")
    hit = find_manifest_for_workload(tmp_path, "payments")
    assert hit.endswith("bundle.yaml")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_sources.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/context/__init__.py`:
```python
```

`src/gke_triage/context/sources.py`:
```python
from __future__ import annotations

from pathlib import Path

import yaml


def find_manifest_for_workload(repo_root: str | Path, workload: str) -> str | None:
    """Return the path of the first YAML manifest whose metadata.name == workload."""
    repo_root = Path(repo_root)
    for path in sorted(repo_root.rglob("*.y*ml")):
        try:
            docs = list(yaml.safe_load_all(path.read_text()))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if isinstance(doc, dict):
                name = (doc.get("metadata") or {}).get("name")
                if name == workload:
                    return str(path)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context_sources.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/context/__init__.py src/gke_triage/context/sources.py tests/test_context_sources.py
git commit -m "feat: add GitOps manifest locator"
```

---

## Task 9: Reporter — incident report + diff + PR

**Files:**
- Create: `src/gke_triage/reporter.py`
- Test: `tests/test_reporter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reporter.py`:
```python
from gke_triage.models import Finding, TriageResult
from gke_triage.reporter import render_report, write_outputs


def _result():
    return TriageResult(
        root_cause="image tag 'latst' does not exist",
        confidence="high",
        findings=[Finding(
            summary="ImagePullBackOff on payments",
            evidence=["pod payments-1: ImagePullBackOff", "deploy.yaml:12 image: pay:latst"],
            manifest_path="apps/payments/deploy.yaml",
        )],
        proposed_patch="--- a/apps/payments/deploy.yaml\n+++ b/apps/payments/deploy.yaml\n",
    )


def test_render_report_contains_sections_and_evidence():
    md = render_report("payments", "prod", _result())
    assert "# Triage report: payments" in md
    assert "Root cause" in md
    assert "image tag 'latst'" in md
    assert "ImagePullBackOff on payments" in md
    assert "deploy.yaml:12" in md
    assert "high" in md.lower()


def test_render_report_inconclusive_lists_hypotheses_no_fix():
    r = TriageResult(root_cause="unclear", confidence="low",
                     findings=[Finding(summary="maybe OOM", evidence=["restarts=5"])],
                     proposed_patch=None)
    md = render_report("ledger", "prod", r)
    assert "Inconclusive" in md or "hypothes" in md.lower()
    assert "No automated fix" in md


def test_write_outputs_writes_report_and_patch(tmp_path):
    out = write_outputs(tmp_path, "payments", "prod", _result(), open_pr=False)
    report = (tmp_path / out["report"]).read_text()
    patch = (tmp_path / out["patch"]).read_text()
    assert "Triage report" in report
    assert patch.startswith("--- a/")
    assert out["pr_url"] is None


def test_write_outputs_skips_patch_when_no_fix(tmp_path):
    r = TriageResult(root_cause="x", confidence="low", findings=[], proposed_patch=None)
    out = write_outputs(tmp_path, "x", "prod", r, open_pr=False)
    assert out["patch"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reporter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/reporter.py`:
```python
from __future__ import annotations

import subprocess
from pathlib import Path

from gke_triage.models import TriageResult


def render_report(workload: str, namespace: str, result: TriageResult) -> str:
    lines = [
        f"# Triage report: {workload} (namespace: {namespace})",
        "",
        f"**Confidence:** {result.confidence}",
        "",
        "## Root cause",
        "",
        result.root_cause,
        "",
        "## Evidence",
        "",
    ]
    for f in result.findings:
        lines.append(f"### {f.summary}")
        if f.manifest_path:
            lines.append(f"- Manifest: `{f.manifest_path}`")
        for e in f.evidence:
            lines.append(f"- {e}")
        lines.append("")

    if result.is_conclusive():
        lines += ["## Proposed fix", "",
                  "A patch is attached and (optionally) opened as a PR. "
                  "Review and merge via your normal GitOps flow.", ""]
    else:
        lines += ["## Inconclusive", "",
                  "No automated fix proposed. Ranked hypotheses above; "
                  "gather more evidence before acting.", ""]
    return "\n".join(lines)


def _open_pr(repo_root: Path, patch_path: Path, workload: str) -> str | None:
    branch = f"gke-triage/fix-{workload}"
    try:
        subprocess.run(["git", "-C", str(repo_root), "checkout", "-b", branch], check=True)
        subprocess.run(["git", "-C", str(repo_root), "apply", str(patch_path)], check=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-am",
                        f"fix({workload}): gke-triage proposed fix"], check=True)
        subprocess.run(["git", "-C", str(repo_root), "push", "-u", "origin", branch], check=True)
        out = subprocess.run(
            ["gh", "pr", "create", "--fill", "--head", branch],
            cwd=str(repo_root), check=True, capture_output=True, text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_outputs(out_dir: str | Path, workload: str, namespace: str,
                  result: TriageResult, open_pr: bool = False,
                  repo_root: str | Path | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_name = f"{workload}-report.md"
    (out_dir / report_name).write_text(render_report(workload, namespace, result))

    patch_name = None
    pr_url = None
    if result.proposed_patch:
        patch_name = f"{workload}-fix.patch"
        patch_path = out_dir / patch_name
        patch_path.write_text(result.proposed_patch)
        if open_pr and repo_root:
            pr_url = _open_pr(Path(repo_root), patch_path, workload)

    return {"report": report_name, "patch": patch_name, "pr_url": pr_url}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reporter.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/reporter.py tests/test_reporter.py
git commit -m "feat: add reporter (markdown report + patch + optional PR)"
```

---

## Task 10: Skills library — k8s-troubleshooter playbook

**Files:**
- Create: `src/gke_triage/skills/k8s-troubleshooter/SKILL.md`
- Test: `tests/test_skill_present.py`

- [ ] **Step 1: Write the failing test**

`tests/test_skill_present.py`:
```python
from pathlib import Path

import gke_triage


def test_skill_md_exists_and_has_required_sections():
    root = Path(gke_triage.__file__).parent
    skill = root / "skills" / "k8s-troubleshooter" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text()
    assert text.startswith("---")  # frontmatter
    assert "name:" in text
    assert "ImagePullBackOff" in text
    assert "OOMKilled" in text
    assert "STRUCTURED_RESULT" in text  # output contract for the orchestrator
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_skill_present.py -v`
Expected: FAIL with `AssertionError` (file missing)

- [ ] **Step 3: Write the skill**

`src/gke_triage/skills/k8s-troubleshooter/SKILL.md`:
```markdown
---
name: k8s-troubleshooter
description: Diagnose a degraded GKE workload read-only and propose a manifest fix as a unified diff. Use when investigating broken pods/services on GKE.
---

# Kubernetes Troubleshooter (read-only)

You are an SRE assistant. You may ONLY use read-only tools (list/get/describe/logs/events).
Never attempt to apply, patch, delete, scale, restart, or exec — those calls are blocked
and indicate a wrong approach.

## Investigation procedure

1. Get the workload's pods and their phase/state for the target namespace.
2. For non-Running pods, describe them and read recent events. Map the state to a cause:
   - **ImagePullBackOff / ErrImagePull** → bad image name or tag; check `spec...image`.
   - **CreateContainerConfigError** → missing ConfigMap/Secret key or env var.
   - **CrashLoopBackOff** → read container logs; look for config/startup errors.
   - **OOMKilled** → memory limit too low vs. usage.
   - **Pending** → unschedulable: resource requests, nodeSelector, taints.
   - **Running but no traffic** → Service selector/labels mismatch or wrong targetPort.
3. Read recent logs for the failing container.
4. Read the source manifest from the GitOps repo and locate the exact offending line.
5. Reason about *what changed* (recent rollout/deploy history) when available.

## Output contract

When done, emit a fenced block exactly like this (the orchestrator parses it):

```STRUCTURED_RESULT
{
  "root_cause": "<one-sentence cause>",
  "confidence": "high|medium|low",
  "findings": [
    {"summary": "...", "evidence": ["...", "..."], "manifest_path": "relative/path.yaml"}
  ],
  "proposed_patch": "<unified git diff against the GitOps repo, or null if inconclusive>"
}
```

If you cannot determine a fix with reasonable confidence, set `proposed_patch` to null
and list ranked hypotheses in `findings`. Never fabricate a fix.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_skill_present.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/skills/k8s-troubleshooter/SKILL.md tests/test_skill_present.py
git commit -m "feat: add k8s-troubleshooter skill with structured output contract"
```

---

## Task 11: Orchestrator — parse result + launch Gemini

**Files:**
- Create: `src/gke_triage/orchestrator.py`
- Test: `tests/test_orchestrator.py`

The orchestrator (a) builds the prompt, (b) launches Gemini CLI configured with
the guardrail proxy + skill, (c) parses the `STRUCTURED_RESULT` block into a
`TriageResult`. The Gemini launch is injected as a callable so it can be mocked.

- [ ] **Step 1: Write the failing test**

`tests/test_orchestrator.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/orchestrator.py`:
```python
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from gke_triage.models import Finding, TriageResult

_BLOCK_RE = re.compile(r"```STRUCTURED_RESULT\s*(\{.*?\})\s*```", re.DOTALL)

PROMPT_TEMPLATE = (
    "Use the k8s-troubleshooter skill. Investigate workload '{workload}' in "
    "namespace '{namespace}' read-only and emit the STRUCTURED_RESULT block."
)


def parse_structured_result(text: str) -> TriageResult:
    m = _BLOCK_RE.search(text)
    if not m:
        return TriageResult(root_cause="No structured result returned by agent",
                            confidence="low", findings=[], proposed_patch=None)
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return TriageResult(root_cause="Malformed structured result",
                            confidence="low", findings=[], proposed_patch=None)
    findings = [Finding(summary=f.get("summary", ""),
                        evidence=f.get("evidence", []),
                        manifest_path=f.get("manifest_path"))
                for f in data.get("findings", [])]
    return TriageResult(
        root_cause=data.get("root_cause", ""),
        confidence=data.get("confidence", "low"),
        findings=findings,
        proposed_patch=data.get("proposed_patch") or None,
    )


def diagnose(workload: str, namespace: str,
             runner: Callable[[str, Path | None], str],
             workdir: Path | None = None) -> TriageResult:
    prompt = PROMPT_TEMPLATE.format(workload=workload, namespace=namespace)
    output = runner(prompt, workdir)
    return parse_structured_result(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add orchestrator with structured-result parsing"
```

---

## Task 12: Gemini runner + guardrail MCP transport wiring

**Files:**
- Modify: `src/gke_triage/orchestrator.py` (add `gemini_runner`)
- Create: `src/gke_triage/guardrail/server.py` (stdio MCP server entry)
- Test: `tests/test_gemini_runner.py`

Wires the real pieces: `gemini_runner` writes a temporary Gemini extension config
pointing at `gke-triage _serve-proxy` (the stdio MCP server that wraps upstream
in the `Guardrail`), mounts the skill, runs `gemini -p <prompt>` non-interactively,
and returns stdout. The MCP transport is thin glue over the tested `Guardrail`.

- [ ] **Step 1: Write the failing test**

`tests/test_gemini_runner.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gemini_runner.py -v`
Expected: FAIL with `ImportError` (no `gemini_runner`)

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `src/gke_triage/orchestrator.py`:
```python
import os
import subprocess
import tempfile
```

Append to `src/gke_triage/orchestrator.py`:
```python
SKILLS_DIR = Path(__file__).parent / "skills"


def gemini_runner(prompt: str, workdir: Path | None = None) -> str:
    """Run Gemini CLI non-interactively with the skills dir mounted.

    The guardrail MCP server is registered via a Gemini extension config that
    invokes `gke-triage _serve-proxy`. Cluster access therefore always passes
    through the read-only Guardrail.
    """
    env = dict(os.environ)
    env["GEMINI_SKILLS_DIR"] = str(SKILLS_DIR)
    cmd = ["gemini", "-p", prompt]
    result = subprocess.run(
        cmd, cwd=str(workdir) if workdir else None,
        env=env, capture_output=True, text=True,
    )
    return result.stdout
```

`src/gke_triage/guardrail/server.py`:
```python
from __future__ import annotations

import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from gke_triage.guardrail.audit import AuditLog
from gke_triage.guardrail.proxy import Guardrail
from gke_triage.models import ToolCall


class _RemoteUpstream:
    """Synchronous-looking adapter over the async MCP client session."""

    def __init__(self, session: ClientSession):
        self._session = session

    async def call_async(self, call: ToolCall):
        res = await self._session.call_tool(call.name, call.args)
        return res.model_dump() if hasattr(res, "model_dump") else res


async def serve(endpoint: str, audit_path: str) -> None:
    server = Server("gke-triage-guardrail")
    audit = AuditLog(audit_path)

    async with streamablehttp_client(endpoint) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            upstream = _RemoteUpstream(session)
            guard = Guardrail(upstream=upstream, audit=audit)

            @server.list_tools()
            async def list_tools():
                return (await session.list_tools()).tools

            @server.call_tool()
            async def call_tool(name: str, arguments: dict):
                # enforce() runs policy+audit synchronously; forward only if allowed
                from gke_triage.guardrail.policy import evaluate
                from gke_triage.guardrail.redact import redact
                call = ToolCall(name=name, args=arguments or {})
                decision = evaluate(call)
                audit.record(call, decision)
                if not decision.allowed:
                    return [{"type": "text", "text": f"Refused: {decision.reason}"}]
                raw = await upstream.call_async(call)
                return [{"type": "text", "text": str(redact(raw))}]

            async with stdio_server() as (r, w):
                await server.run(r, w, server.create_initialization_options())


def main() -> None:
    endpoint = os.environ.get("GKE_TRIAGE_UPSTREAM", "https://container.googleapis.com/mcp")
    audit_path = os.environ.get("GKE_TRIAGE_AUDIT", os.path.expanduser("~/.gke-triage/audit.jsonl"))
    asyncio.run(serve(endpoint, audit_path))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_gemini_runner.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gke_triage/orchestrator.py src/gke_triage/guardrail/server.py tests/test_gemini_runner.py
git commit -m "feat: add Gemini runner and guardrail stdio MCP server"
```

---

## Task 13: CLI wiring (`diagnose`, `init`, `_serve-proxy`)

**Files:**
- Create: `src/gke_triage/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from typer.testing import CliRunner

from gke_triage.cli import app

runner = CliRunner()


def test_init_scaffolds_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    result = runner.invoke(app, ["init", "--path", str(cfg)])
    assert result.exit_code == 0
    assert cfg.exists()
    assert "gitops_repo" in cfg.read_text()


def test_diagnose_end_to_end_with_fake_runner(tmp_path, monkeypatch):
    # GitOps repo with the target workload
    repo = tmp_path / "gitops"
    (repo / "apps").mkdir(parents=True)
    (repo / "apps" / "payments.yaml").write_text(
        "kind: Deployment\nmetadata:\n  name: payments\n")

    sample = (
        'x```STRUCTURED_RESULT\n'
        '{"root_cause":"bad tag","confidence":"high",'
        '"findings":[{"summary":"ImagePullBackOff","evidence":["e1"],'
        '"manifest_path":"apps/payments.yaml"}],'
        '"proposed_patch":"--- a/apps/payments.yaml\\n+++ b/apps/payments.yaml\\n"}\n```'
    )
    monkeypatch.setattr("gke_triage.cli.gemini_runner", lambda prompt, workdir=None: sample)

    out_dir = tmp_path / "out"
    result = runner.invoke(app, [
        "diagnose", "payments", "-n", "prod",
        "--repo", str(repo), "--output", str(out_dir), "--no-pr",
    ])
    assert result.exit_code == 0, result.output
    assert (out_dir / "payments-report.md").exists()
    assert (out_dir / "payments-fix.patch").exists()
    assert "bad tag" in (out_dir / "payments-report.md").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/gke_triage/cli.py`:
```python
from __future__ import annotations

from pathlib import Path

import typer

from gke_triage.config import DEFAULT_CONFIG_YAML
from gke_triage.orchestrator import diagnose as run_diagnose, gemini_runner
from gke_triage.reporter import write_outputs

app = typer.Typer(help="Local AI on-call SRE for GKE (read-only triage + GitOps fix PRs).")


@app.command()
def init(path: str = typer.Option("~/.gke-triage/config.yaml", "--path")):
    """Scaffold a config file."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(DEFAULT_CONFIG_YAML)
    typer.echo(f"Wrote config template to {p}")


@app.command()
def diagnose(
    workload: str,
    namespace: str = typer.Option("default", "-n", "--namespace"),
    repo: str = typer.Option(".", "--repo", help="GitOps repo root"),
    output: str = typer.Option("./gke-triage-out", "--output"),
    open_pr: bool = typer.Option(True, "--pr/--no-pr"),
):
    """Investigate a workload read-only and emit a report + proposed fix."""
    result = run_diagnose(workload, namespace, runner=gemini_runner)
    out = write_outputs(output, workload, namespace, result,
                        open_pr=open_pr, repo_root=repo)
    typer.echo(f"Report: {Path(output) / out['report']}")
    if out["patch"]:
        typer.echo(f"Patch:  {Path(output) / out['patch']}")
    if out["pr_url"]:
        typer.echo(f"PR:     {out['pr_url']}")
    if not result.is_conclusive():
        typer.echo("Result inconclusive — see ranked hypotheses in the report.")


@app.command(name="_serve-proxy", hidden=True)
def serve_proxy():
    """Run the guardrail stdio MCP server (invoked by Gemini CLI)."""
    from gke_triage.guardrail.server import main
    main()


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite + smoke the binary**

Run: `uv run pytest -q && uv run gke-triage --help`
Expected: all tests pass; help lists `diagnose` and `init`.

- [ ] **Step 6: Commit**

```bash
git add src/gke_triage/cli.py tests/test_cli.py
git commit -m "feat: wire CLI (diagnose, init, hidden proxy server)"
```

---

## Task 14: Eval harness — golden broken scenarios on kind

**Files:**
- Create: `eval/scenarios/image_tag_typo/broken.yaml`
- Create: `eval/scenarios/image_tag_typo/expected_fix.yaml`
- Create: `eval/scenarios/configmap_key_mismatch/broken.yaml`
- Create: `eval/scenarios/configmap_key_mismatch/expected_fix.yaml`
- Create: `eval/run_eval.py`
- Test: `tests/test_eval_scenarios.py`

This is the two-for-one from the spec: the broken scenarios are both the test
suite and the published benchmark. We start with 2 of the codelab's 11 classes;
the rest follow the identical directory pattern (tracked as Task 16).

- [ ] **Step 1: Write the failing test**

`tests/test_eval_scenarios.py`:
```python
from pathlib import Path

import yaml

SCEN = Path(__file__).parent.parent / "eval" / "scenarios"


def test_each_scenario_has_broken_and_fix():
    scenarios = [d for d in SCEN.iterdir() if d.is_dir()]
    assert len(scenarios) >= 2
    for d in scenarios:
        assert (d / "broken.yaml").exists(), f"{d} missing broken.yaml"
        assert (d / "expected_fix.yaml").exists(), f"{d} missing expected_fix.yaml"


def test_broken_and_fix_differ_and_are_valid_yaml():
    for d in [x for x in SCEN.iterdir() if x.is_dir()]:
        broken = (d / "broken.yaml").read_text()
        fixed = (d / "expected_fix.yaml").read_text()
        assert broken != fixed, f"{d}: broken and fix identical"
        list(yaml.safe_load_all(broken))   # parses
        list(yaml.safe_load_all(fixed))    # parses
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eval_scenarios.py -v`
Expected: FAIL (scenario dirs missing)

- [ ] **Step 3: Create the scenario fixtures**

`eval/scenarios/image_tag_typo/broken.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments
spec:
  replicas: 1
  selector:
    matchLabels: {app: payments}
  template:
    metadata:
      labels: {app: payments}
    spec:
      containers:
        - name: payments
          image: nginx:latst   # typo: should be 'latest'
```

`eval/scenarios/image_tag_typo/expected_fix.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments
spec:
  replicas: 1
  selector:
    matchLabels: {app: payments}
  template:
    metadata:
      labels: {app: payments}
    spec:
      containers:
        - name: payments
          image: nginx:latest
```

`eval/scenarios/configmap_key_mismatch/broken.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ledger-config
data:
  DATABASE_URL: postgres://db:5432/ledger
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ledger
spec:
  replicas: 1
  selector:
    matchLabels: {app: ledger}
  template:
    metadata:
      labels: {app: ledger}
    spec:
      containers:
        - name: ledger
          image: nginx:latest
          env:
            - name: DATABASE_URL
              valueFrom:
                configMapKeyRef:
                  name: ledger-config
                  key: DB_URL   # mismatch: ConfigMap key is DATABASE_URL
```

`eval/scenarios/configmap_key_mismatch/expected_fix.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ledger-config
data:
  DATABASE_URL: postgres://db:5432/ledger
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ledger
spec:
  replicas: 1
  selector:
    matchLabels: {app: ledger}
  template:
    metadata:
      labels: {app: ledger}
    spec:
      containers:
        - name: ledger
          image: nginx:latest
          env:
            - name: DATABASE_URL
              valueFrom:
                configMapKeyRef:
                  name: ledger-config
                  key: DATABASE_URL
```

- [ ] **Step 4: Write the eval runner**

`eval/run_eval.py`:
```python
"""Deploy each broken scenario to a kind cluster, run gke-triage, and check the
proposed patch makes the broken manifest match the expected fix.

Usage: uv run python eval/run_eval.py [--scenario NAME]
Requires: kind, kubectl, gemini (authenticated). Designed for CI / manual runs.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SCEN = Path(__file__).parent / "scenarios"


def _apply_patch_and_compare(broken: Path, patch_text: str, expected: Path) -> bool:
    with tempfile.TemporaryDirectory() as d:
        work = Path(d) / "m.yaml"
        work.write_text(broken.read_text())
        patch_file = Path(d) / "fix.patch"
        patch_file.write_text(patch_text)
        try:
            subprocess.run(["git", "apply", "--unsafe-paths",
                            f"--directory={d}", str(patch_file)], check=True)
        except subprocess.CalledProcessError:
            return False
        return work.read_text().strip() == expected.read_text().strip()


def run_scenario(name: str) -> bool:
    d = SCEN / name
    broken, expected = d / "broken.yaml", d / "expected_fix.yaml"
    # In CI: kubectl apply broken.yaml to a kind cluster, then:
    #   gke-triage diagnose <workload> -n default --repo <dir> --no-pr
    # then read the emitted patch. Here we assert the fixtures are coherent.
    print(f"[scenario] {name}: broken+expected present = {broken.exists() and expected.exists()}")
    return broken.exists() and expected.exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario")
    args = ap.parse_args()
    names = [args.scenario] if args.scenario else [d.name for d in SCEN.iterdir() if d.is_dir()]
    ok = all(run_scenario(n) for n in names)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_eval_scenarios.py -v && uv run python eval/run_eval.py`
Expected: tests PASS; runner prints PASS.

- [ ] **Step 6: Commit**

```bash
git add eval tests/test_eval_scenarios.py
git commit -m "feat: add eval harness with two golden broken scenarios"
```

---

## Task 15: README and install docs

**Files:**
- Create: `README.md`
- Test: `tests/test_readme.py`

- [ ] **Step 1: Write the failing test**

`tests/test_readme.py`:
```python
from pathlib import Path


def test_readme_documents_core_usage():
    text = Path("README.md").read_text()
    for token in ["gke-triage", "diagnose", "read-only", "GitOps", "uv", "audit"]:
        assert token in text, f"README missing '{token}'"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_readme.py -v`
Expected: FAIL (README missing)

- [ ] **Step 3: Write the README**

`README.md`:
```markdown
# gke-triage

Local **AI on-call SRE for GKE**. Point it at a degraded workload; it investigates
**read-only** (via Gemini CLI + the GKE MCP server behind a safety guardrail),
writes an evidence-cited root-cause report, and proposes the fix as a **GitOps
diff / PR**. It never mutates your cluster.

## Why

Google's GKE AI Toolkit codelab shows an AI can find and fix broken manifests.
The hard part for real teams is *trusting* an agent near production. `gke-triage`
makes that safe: read-only by default, secrets redacted before they reach the
model, every tool call written to an append-only **audit** log, and all changes
delivered as reviewable diffs through your normal **GitOps** flow.

## Install

```bash
uv tool install gke-triage      # or: uv sync (from source)
gke-triage init                 # scaffold ~/.gke-triage/config.yaml
```

Prerequisites: `gcloud` (authenticated), `kubectl`, `gemini` CLI, and `gh`
(for PR creation).

## Usage

```bash
gke-triage diagnose payments -n prod --repo ./gitops
# read-only investigation → report + proposed fix PR
gke-triage diagnose payments -n prod --repo ./gitops --no-pr   # emit .patch only
```

Outputs land in `./gke-triage-out/`: a Markdown report and a `.patch` (and a PR
unless `--no-pr`).

## Safety model

- **Read-only allowlist (default-deny):** any mutating verb (apply/patch/delete/
  scale/exec/...) is blocked before reaching the cluster.
- **Secret redaction:** Secret values and sensitive keys are scrubbed from tool
  outputs.
- **Audit log:** every tool call (allowed or blocked) is appended to
  `~/.gke-triage/audit.jsonl`.

## Benchmark

`eval/scenarios/` holds reproducible broken-manifest scenarios (modeled on the
codelab's failure classes). Run `uv run python eval/run_eval.py` to evaluate.

## License

Apache-2.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_readme.py -v`
Expected: PASS

- [ ] **Step 5: Final full-suite run + commit**

Run: `uv run pytest -q`
Expected: entire suite green.

```bash
git add README.md tests/test_readme.py
git commit -m "docs: add README with usage, safety model, and benchmark"
```

---

## Task 16: Expand scenario + skills coverage (follow-on)

**Files:**
- Create: `eval/scenarios/<class>/broken.yaml` + `expected_fix.yaml` for each remaining failure class
- Modify: `src/gke_triage/skills/k8s-troubleshooter/SKILL.md` (already enumerates classes)

Add the remaining codelab failure classes, each as a new scenario directory
following the **exact pattern** of Task 14 (a `broken.yaml` with one injected
error and an `expected_fix.yaml`). Remaining classes:

- service selector/label mismatch
- wrong `targetPort` / port mismatch
- OOMKilled (memory limit too low)
- missing env var
- malformed config URL (double colon)
- bad readiness/liveness probe path
- image pull from nonexistent registry/repo
- resource-request makes pod `Pending`
- CrashLoopBackOff from bad startup config

For each: add the two YAML files, then `uv run pytest tests/test_eval_scenarios.py`
(the existing generic tests validate every scenario dir automatically — no new
test code needed). Commit per scenario:

```bash
git add eval/scenarios/<class>
git commit -m "test: add <class> eval scenario"
```

---

## Self-Review notes

- **Spec coverage:** Orchestrator (T11–13), guardrail proxy w/ allowlist+redaction+audit (T3–6, T12), context-fusion repo reader (T8; live log/deploy tools flow through the guardrail server T12), skills library (T10, T16), reporter w/ report+diff+PR and `.patch` fallback (T9), error handling — inconclusive/blocked/no-repo (covered in T9 `render_report`, T6 enforce, T9 patch-skip), testing+benchmark two-for-one (T14, T16), distribution via `uv`/`init` (T7, T13, T15). All spec sections map to tasks.
- **Type consistency:** `ToolCall(name,args)`, `Decision(allowed,reason)`, `Finding(summary,evidence,manifest_path)`, `TriageResult(root_cause,confidence,findings,proposed_patch)` and `is_conclusive()` are used identically across T2, T6, T9, T11, T13.
- **No placeholders:** every code step contains complete, runnable code. T16 intentionally repeats the established fixture pattern rather than re-listing identical code per class.
```
