# gke-triage

Local **AI on-call SRE for GKE**. Point it at a degraded workload; it investigates
**read-only** (via the Antigravity CLI (`agy`, powered by Gemini) + the GKE MCP server behind a safety guardrail),
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

Prerequisites: `gcloud` (authenticated), `kubectl`, `agy` (Antigravity CLI) — or `gemini` (Gemini CLI) with `--engine gemini`, and `gh`
(for PR creation).

## Register the guardrail with your engine

`gke-triage` runs the agent behind a read-only guardrail MCP server. Register it once:

```bash
gke-triage register   # writes ~/.gemini/config/mcp_config.json + installs the skill
```

This adds a local stdio MCP server `gke-triage-guardrail` (the Antigravity CLI launches
`gke-triage _serve-proxy`, which proxies the GKE MCP server behind the read-only guardrail)
and installs the `k8s-troubleshooter` skill to `~/.gemini/skills/`. `gke-triage diagnose`
also performs this registration automatically when using the default `antigravity` engine.

## Usage

```bash
gke-triage diagnose payments -n prod --repo ./gitops
# read-only investigation -> report + proposed fix PR
gke-triage diagnose payments -n prod --repo ./gitops --no-pr   # emit .patch only
gke-triage diagnose payments -n prod --repo ./gitops --engine gemini   # use Gemini CLI instead
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
