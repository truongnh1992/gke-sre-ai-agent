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
