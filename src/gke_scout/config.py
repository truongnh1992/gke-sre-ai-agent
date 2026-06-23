from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_ENDPOINT = "https://container.googleapis.com/mcp"
DEFAULT_AUDIT = "~/.gke-scout/audit.jsonl"

DEFAULT_CONFIG_YAML = f"""\
# gke-scout configuration
upstream_mcp_endpoint: {DEFAULT_ENDPOINT}
audit_log: {DEFAULT_AUDIT}
engine: antigravity            # reasoning engine: antigravity (agy) or gemini
"""


@dataclass
class Config:
    upstream_mcp_endpoint: str = DEFAULT_ENDPOINT
    audit_log: str = DEFAULT_AUDIT
    engine: str = "antigravity"

    def __post_init__(self):
        self.audit_log = str(Path(self.audit_log).expanduser())


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return Config(
        upstream_mcp_endpoint=data.get("upstream_mcp_endpoint", DEFAULT_ENDPOINT),
        audit_log=data.get("audit_log", DEFAULT_AUDIT),
        engine=data.get("engine", "antigravity"),
    )
