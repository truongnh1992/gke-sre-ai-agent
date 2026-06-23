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
    "watch", "top", "explain", "version", "diff",
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
