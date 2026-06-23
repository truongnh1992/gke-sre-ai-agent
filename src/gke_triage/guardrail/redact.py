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
_BEARER_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9._\-+/=]{8,})")


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in SENSITIVE_KEY_SUBSTRINGS)


def _redact_node(node, parent_is_secret: bool):
    if isinstance(node, dict):
        # Special case: an env entry {name: API_KEY, value: ...}
        if "name" in node and "value" in node and _is_sensitive_key(str(node["name"])):
            out = {k: _redact_node(v, parent_is_secret) for k, v in node.items() if k != "value"}
            out["value"] = REDACTED
            return out
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
        rest = {k: v for k, v in payload.items() if k != "data"}
        walked = _redact_node(rest, False)
        walked["data"] = payload["data"]
        return walked
    return _redact_node(payload, False)
