from __future__ import annotations

import json
import shutil
from pathlib import Path

_BUNDLED_SKILLS = Path(__file__).parent / "skills"

DEFAULT_MCP_CONFIG = "~/.gemini/config/mcp_config.json"
DEFAULT_SKILLS_DIR = "~/.gemini/skills"
GUARDRAIL_SERVER_NAME = "gke-triage-guardrail"


def guardrail_server_entry(upstream: str, audit_path: str,
                           command: str = "gke-triage") -> dict:
    """Build the Antigravity mcp_config.json entry for the local guardrail proxy.

    Registered as a LOCAL stdio server: the CLI launches `gke-triage _serve-proxy`,
    which forwards to the real GKE MCP server (GKE_TRIAGE_UPSTREAM) behind the
    read-only guardrail. The CLI never talks to the cluster directly.
    """
    return {
        "command": command,
        "args": ["_serve-proxy"],
        "env": {
            "GKE_TRIAGE_UPSTREAM": upstream,
            "GKE_TRIAGE_AUDIT": audit_path,
        },
    }


def register_mcp_server(config_path: str | Path, name: str, entry: dict) -> None:
    """Merge a server entry into an Antigravity mcp_config.json (idempotent).

    Preserves any existing servers and top-level keys. Creates the file and
    parent directories if absent. Tolerates an empty/corrupt file by starting fresh.
    """
    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text() or "{}")
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[name] = entry
    data["mcpServers"] = servers
    config_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def install_skill(skills_dir: str | Path, skill_name: str = "k8s-troubleshooter") -> str:
    """Copy the bundled SKILL.md into the Antigravity skills dir. Returns its path."""
    skills_dir = Path(skills_dir).expanduser()
    dest_dir = skills_dir / skill_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = _BUNDLED_SKILLS / skill_name / "SKILL.md"
    dest = dest_dir / "SKILL.md"
    shutil.copyfile(src, dest)
    return str(dest)


def ensure_antigravity_setup(upstream: str, audit_path: str,
                             config_path: str | Path = DEFAULT_MCP_CONFIG,
                             skills_dir: str | Path = DEFAULT_SKILLS_DIR,
                             command: str = "gke-triage") -> dict:
    """Register the guardrail MCP server and install the skill for Antigravity CLI.

    Idempotent; safe to call before every run. Returns the resolved paths.
    """
    register_mcp_server(config_path, GUARDRAIL_SERVER_NAME,
                        guardrail_server_entry(upstream, audit_path, command))
    skill_path = install_skill(skills_dir)
    return {
        "config_path": str(Path(config_path).expanduser()),
        "skill_path": skill_path,
        "server_name": GUARDRAIL_SERVER_NAME,
    }
