# gke-sre-ai-agent

> Ships the **`gke-triage`** CLI (install from source with `uv tool install .`).

Local **AI on-call SRE for GKE**. Point it at a degraded workload; it investigates
**read-only** (via the Antigravity CLI (`agy`, powered by Gemini) + the GKE MCP server behind a safety guardrail)
and writes an evidence-cited root-cause report. It never mutates your cluster.

## Why

An AI can find broken workloads quickly, but the hard part for real teams is
*trusting* an agent near production. `gke-triage` makes it safe: read-only by
default, secrets redacted before they reach the model, and every tool call
written to an append-only **audit** log. It only ever reports a diagnosis — it
never changes your cluster or your manifests.

## Install

```bash
uv tool install .               # install from local source
gke-triage init                 # scaffold ~/.gke-triage/config.yaml
```

Prerequisites: `gcloud` (authenticated), `kubectl`, and `agy` (Antigravity CLI) — or
`gemini` (Gemini CLI) with `--engine gemini`.

## Register the guardrail with your engine

`gke-triage` runs the agent behind a read-only guardrail MCP server. Register it once:

```bash
gke-triage register   # writes ~/.gemini/config/mcp_config.json + installs the skill
```

This adds a local stdio MCP server `gke-triage-guardrail` (the Antigravity CLI launches
`gke-triage _serve-proxy`, which proxies the GKE MCP server behind the read-only guardrail)
and installs the `k8s-troubleshooter` skill to `~/.gemini/skills/`. `gke-triage diagnose`
also performs this registration automatically when using the default `antigravity` engine.

The Antigravity CLI keeps its own plugin registry. Import the Gemini-side config
(guardrail MCP server + skill) into `agy` once:

```bash
agy plugin import gemini
```

For the `antigravity` engine, `gke-triage` also inlines the `k8s-troubleshooter`
instructions directly into the prompt and runs `agy` non-interactively with
`--dangerously-skip-permissions --print-timeout 15m`, so investigations complete
without manual approval prompts and have headroom for multi-step cases.

## Usage

```bash
gke-triage diagnose ${YOUR-DEPLOYMENT} -n ${YOUR-NAMESPACE}
# read-only investigation -> evidence-cited report
gke-triage diagnose ${YOUR-DEPLOYMENT} -n ${YOUR-NAMESPACE} --engine gemini   # use Gemini CLI instead
gke-triage diagnose ${YOUR-DEPLOYMENT} -n ${YOUR-NAMESPACE} --verbose         # dump raw engine output
```

Outputs land in `./gke-triage-out/`: a Markdown root-cause report containing the
root cause, a confidence level (`high`/`medium`/`low`), and evidence-cited
findings. Low-confidence runs instead list ranked hypotheses.

A live spinner with an elapsed-time counter is shown while the agent runs. A
diagnosis is an autonomous, multi-step investigation (list/describe pods, read
events and logs), so runs typically take a few minutes; genuinely broken,
multi-issue workloads take longer. Healthy workloads (all pods Ready, no
restarts, no warning events) short-circuit early and return in seconds. Use
`--verbose` to print the raw engine output when a run ends up inconclusive.

## Safety model

- **Read-only allowlist (default-deny):** any mutating verb (apply/patch/delete/
  scale/exec/...) is blocked before reaching the cluster.
- **Secret redaction:** Secret values and sensitive keys are scrubbed from tool
  outputs.
- **Audit log:** every tool call (allowed or blocked) is appended to
  `~/.gke-triage/audit.jsonl`.

## Benchmark

`eval/scenarios/` holds reproducible broken-workload scenarios covering common
failure classes. Run `uv run python eval/run_eval.py` to evaluate.

## License

Apache-2.0
