import json
from pathlib import Path

from gke_triage.engines import (
    guardrail_server_entry, register_mcp_server, install_skill,
    ensure_antigravity_setup, GUARDRAIL_SERVER_NAME,
)


def test_guardrail_server_entry_shape():
    e = guardrail_server_entry("https://up/mcp", "/a/audit.jsonl")
    assert e["command"] == "gke-triage"
    assert e["args"] == ["_serve-proxy"]
    assert e["env"]["GKE_TRIAGE_UPSTREAM"] == "https://up/mcp"
    assert e["env"]["GKE_TRIAGE_AUDIT"] == "/a/audit.jsonl"


def test_register_creates_file_with_mcpservers(tmp_path):
    cfg = tmp_path / "mcp_config.json"
    register_mcp_server(cfg, "gke-triage-guardrail", {"command": "x"})
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["gke-triage-guardrail"]["command"] == "x"


def test_register_preserves_existing_servers_and_keys(tmp_path):
    cfg = tmp_path / "mcp_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "o"}}, "foo": 1}))
    register_mcp_server(cfg, "gke-triage-guardrail", {"command": "x"})
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["other"]["command"] == "o"
    assert data["mcpServers"]["gke-triage-guardrail"]["command"] == "x"
    assert data["foo"] == 1


def test_register_idempotent(tmp_path):
    cfg = tmp_path / "mcp_config.json"
    register_mcp_server(cfg, "n", {"command": "x"})
    register_mcp_server(cfg, "n", {"command": "x"})
    data = json.loads(cfg.read_text())
    assert list(data["mcpServers"].keys()) == ["n"]


def test_register_tolerates_corrupt_file(tmp_path):
    cfg = tmp_path / "mcp_config.json"
    cfg.write_text("{not valid json")
    register_mcp_server(cfg, "n", {"command": "x"})
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["n"]["command"] == "x"


def test_install_skill_copies_skill_md(tmp_path):
    dest = tmp_path / "skills"
    out = Path(install_skill(dest))
    assert out.exists()
    assert out.name == "SKILL.md"
    assert "k8s-troubleshooter" in str(out)
    assert "STRUCTURED_RESULT" in out.read_text()


def test_ensure_antigravity_setup_wires_both(tmp_path):
    cfg = tmp_path / "mcp_config.json"
    skills = tmp_path / "skills"
    info = ensure_antigravity_setup(upstream="https://up/mcp", audit_path="/a.jsonl",
                                    config_path=cfg, skills_dir=skills)
    data = json.loads(cfg.read_text())
    assert GUARDRAIL_SERVER_NAME in data["mcpServers"]
    assert data["mcpServers"][GUARDRAIL_SERVER_NAME]["env"]["GKE_TRIAGE_UPSTREAM"] == "https://up/mcp"
    assert (skills / "k8s-troubleshooter" / "SKILL.md").exists()
    assert info["server_name"] == GUARDRAIL_SERVER_NAME
