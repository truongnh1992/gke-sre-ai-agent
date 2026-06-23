# gke-triage — Design Spec

**Date:** 2026-06-23
**Status:** Approved design, pre-implementation
**Working name:** `gke-triage` (changeable)

## One-line

An open-source, local CLI "AI on-call SRE" for GKE: it investigates a degraded
workload **read-only**, produces an evidence-cited root-cause report, and emits
the fix as a **git diff / PR** for a human to merge via GitOps. It never mutates
the cluster.

## Background & motivation

Google's [AI Toolkit codelab](https://codelabs.developers.google.com/codelabs/gke/ai-toolkit-lab-1)
proves that **Gemini CLI + the GKE MCP server** can find and fix broken
Kubernetes manifests when given full cluster context. That's a teaching demo.

The gap for a real platform/SRE team is **not** finding the bug — it's that
letting an AI touch a production cluster is unacceptable without governance.
`gke-triage` closes that gap: autonomous investigation, but every *change* flows
through review and GitOps, with a full audit trail and secret redaction.

This is the differentiator from the codelab. The debugging cleverness is
table-stakes (the GKE MCP server already provides it); **safety, evidence, and
reviewable proposed fixes** are the product.

## Goals

- A tool a platform/SRE team would actually point at a real GKE cluster.
- Read-only by default; all fixes are proposed as diffs/PRs, never applied.
- Reasons about *what changed* (logs, deploy history, events), not just current state.
- Reproducible: ships a benchmark of known-broken scenarios.
- Easy install ergonomics (batteries-included distribution).

## Non-goals (YAGNI for v1)

- In-cluster always-on operator / event-driven auto-triage (roadmap stretch, "Cluster Guardian").
- Direct cluster mutation, even approval-gated (explicitly excluded by chosen safety posture).
- CI pre-merge PR-review mode (possible v2; not in scope now).
- Non-GKE / generic Kubernetes support (GKE-first; the GKE MCP server is the backbone).

## Decisions (locked)

| Decision | Choice |
|---|---|
| Primary goal | Reusable production troubleshooter for SRE teams |
| Audience | Platform / SRE engineers |
| Safety posture | **Read-only + propose PR** (no apply, even gated) |
| Form factor | **Local CLI** run against the operator's kubeconfig context |
| Reasoning engine | **Gemini CLI** |
| Orchestrator + guardrail language | **Python** (pip/uv distribution) |

## Architecture

Five components, each independently understandable and testable.

```
                 ┌─────────────────────────────────────────────┐
  SRE  ── runs ─▶│  Orchestrator (CLI)                          │
                 │  `gke-triage diagnose <workload> -n <ns>`    │
                 │  loads skills, drives investigate→report→fix │
                 └───────────────┬─────────────────────────────┘
                                 │ launches Gemini CLI (reasoning engine)
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  Guardrail MCP proxy  (the keystone)         │
                 │  • read-only allowlist (block apply/patch/   │
                 │    delete/scale/exec-write)                  │
                 │  • secret redaction on tool outputs         │
                 │  • append-only audit log of every call      │
                 └───────┬───────────────────────┬─────────────┘
                         ▼                        ▼
              ┌────────────────────┐   ┌──────────────────────────┐
              │ GKE MCP server     │   │ Context-fusion sources   │
              │ (cluster state,    │   │ • Cloud Logging          │
              │  events, logs)     │   │ • rollout/deploy history │
              └────────────────────┘   │ • GitOps repo manifests  │
                                        └──────────────────────────┘
                                 │
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  Reporter / fix-proposer                     │
                 │  • Markdown incident report (cited evidence) │
                 │  • diff vs GitOps repo → PR (gh) or .patch   │
                 └─────────────────────────────────────────────┘
```

### 1. Orchestrator (CLI)
- Entrypoint: `gke-triage diagnose <workload> -n <namespace>` (plus `--repo`,
  `--output`, `--no-pr`, `--context` flags).
- Resolves kubeconfig context, configures and launches Gemini CLI with the
  skills library mounted and the guardrail proxy as the MCP endpoint.
- Owns the investigate → report → propose state machine.
- **Interface:** CLI in, structured `TriageResult` (root cause + evidence +
  proposed change) out.

### 2. Guardrail MCP proxy *(keystone)*
- A local MCP server that the agent talks to; it forwards to the real GKE MCP
  server (and other context tools) only for **read/list/get** operations.
- **Read-only allowlist:** any mutating verb is rejected before forwarding,
  the rejection is logged, and a clear message is surfaced.
- **Secret redaction:** Secret values, and known sensitive keys, are scrubbed
  from tool outputs before they reach the model.
- **Audit log:** append-only (JSONL) record of every tool call, args, and
  decision (forwarded / blocked / redacted).
- **Interface:** speaks MCP to the agent; config = upstream endpoints + policy file.

### 3. Context-fusion layer
- Pulls beyond current state: Cloud Logging entries for the workload, recent
  rollout/deploy history, cluster events, and the source manifests from the
  configured GitOps repo.
- Surfaced to the agent as additional read-only MCP tools (behind the guardrail).
- Enables "what changed" reasoning, which the codelab lacks.

### 4. Skills library
- Agent Skills (`SKILL.md` playbooks) per failure class, generalizing the
  codelab's `k8s-troubleshooter`. Initial set:
  ImagePullBackOff, OOMKilled, CrashLoopBackOff, Service/selector mismatch,
  ConfigMap key/drift, bad readiness/liveness probe path, malformed config URL,
  missing env var, resource-limit violation, image-tag typo, port mismatch.
- Each skill = symptom signature + investigation steps + fix pattern.

### 5. Reporter / fix-proposer
- Converts the agent's root cause into:
  - **(a)** a Markdown incident report — symptom → evidence (cited logs/events/
    manifest line numbers) → root cause → recommended fix.
  - **(b)** a diff against the GitOps repo, opened as a PR via `gh`, or written
    as a `.patch` file if no repo is configured (`--no-pr`).
- **Never applies** the change.

## Data flow (happy path)

1. SRE runs `gke-triage diagnose payments -n prod --repo ./gitops`.
2. Orchestrator launches Gemini CLI + skills + guardrailed MCP.
3. Agent investigates read-only: cluster state, events, logs, deploy history,
   GitOps manifests.
4. Agent emits a structured root cause + intended change.
5. Reporter locates the offending manifest, generates a diff, writes the report,
   opens a PR.
6. Audit log persisted; SRE reviews report + PR and merges via normal GitOps.

## Error handling

| Situation | Behavior |
|---|---|
| Root cause inconclusive | Report **ranked hypotheses** + evidence gathered. Never fabricate a fix. |
| Agent attempts a mutating call | Guardrail blocks, logs, surfaces to user. |
| No GitOps repo configured | Emit `.patch` file instead of a PR. |
| Offending manifest not found in repo | Report includes the proposed change as inline YAML + a note. |
| GKE MCP / auth failure | Fail fast with an actionable auth/setup message. |

## Testing & benchmark (two-for-one)

- Fixtures harness in the spirit of the codelab's `break.sh`: deploy known-broken
  manifests to a **kind** cluster (or throwaway GKE), run the agent, assert the
  **proposed diff resolves** each scenario.
- The **11 codelab error classes are the golden scenarios** — they serve as both
  the test suite and a reproducible benchmark advertised in the README.
- Unit tests target each component in isolation: guardrail allowlist/redaction
  logic, reporter diff generation, context-fusion adapters (mocked).

## Distribution

- pip / uv installable. `gke-triage init` scaffolds config
  (`~/.gke-triage/config.yaml`: GitOps repo, policy, upstream MCP endpoints) and
  verifies prerequisites (`gcloud`, `kubectl`, `gemini`, `gh`).

## Open questions / roadmap

- v2: CI pre-merge mode (review K8s manifest PRs against live cluster context).
- v2: tiered/policy-driven auto-apply for low-risk fixes.
- Stretch: "Cluster Guardian" in-cluster operator (Approach B).
- Multi-cluster fleet triage.
```
