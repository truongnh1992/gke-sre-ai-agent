from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from gke_scout.models import Finding, TriageResult

_BLOCK_RE = re.compile(r"```STRUCTURED_RESULT\s*(\{.*?\})\s*```", re.DOTALL)

GEMINI_PROMPT_TEMPLATE = (
    "Use the k8s-troubleshooter skill. Investigate workload '{workload}' in "
    "namespace '{namespace}' read-only and emit the STRUCTURED_RESULT block."
)

_SKILL_PATH = Path(__file__).parent / "skills" / "k8s-troubleshooter" / "SKILL.md"

INLINE_PROMPT_TEMPLATE = """\
Investigate workload '{workload}' in namespace '{namespace}'.
{cluster_context}
IMPORTANT: Use ONLY the MCP tools from the gke-scout-guardrail server to query the
cluster. Do NOT use shell commands like kubectl or gcloud — they will not work.

Follow these instructions exactly:

{skill_content}
"""


def _get_cluster_context() -> str:
    """Parse the current kubectl context to extract project/location/cluster for the prompt."""
    try:
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True, text=True, timeout=5)
        ctx = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if not ctx:
        return ""
    parts = ctx.split("_")
    if len(parts) >= 4 and parts[0] == "gke":
        project, location, cluster = parts[1], parts[2], "_".join(parts[3:])
        return (
            f"\nCluster context (skip discovery, use these directly):\n"
            f"  project: {project}\n"
            f"  location: {location}\n"
            f"  cluster: {cluster}\n"
            f"  parent: projects/{project}/locations/{location}/clusters/{cluster}\n"
        )
    return f"\nkubectl context: {ctx}\n"


def _build_prompt(workload: str, namespace: str, *, inline_skill: bool) -> str:
    if inline_skill:
        skill_content = _SKILL_PATH.read_text()
        return INLINE_PROMPT_TEMPLATE.format(
            workload=workload, namespace=namespace,
            skill_content=skill_content,
            cluster_context=_get_cluster_context())
    return GEMINI_PROMPT_TEMPLATE.format(workload=workload, namespace=namespace)


def parse_structured_result(text: str) -> TriageResult:
    m = _BLOCK_RE.search(text)
    if not m:
        return TriageResult(root_cause="No structured result returned by agent",
                            confidence="low", findings=[])
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return TriageResult(root_cause="Malformed structured result",
                            confidence="low", findings=[])
    findings = [Finding(summary=f.get("summary", ""),
                        evidence=f.get("evidence", []))
                for f in data.get("findings", [])]
    return TriageResult(
        root_cause=data.get("root_cause", ""),
        confidence=data.get("confidence", "low"),
        findings=findings,
    )


SKILLS_DIR = Path(__file__).parent / "skills"

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class _Spinner:
    """Animated terminal spinner shown on stderr while an engine runs."""

    def __init__(self, message: str) -> None:
        self._message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "_Spinner":
        self._t0 = time.monotonic()
        if sys.stderr.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            sys.stderr.write(f"{self._message}...\n")
            sys.stderr.flush()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()

    def _spin(self) -> None:
        for frame in itertools.cycle(_SPINNER_FRAMES):
            if self._stop.is_set():
                break
            elapsed = int(time.monotonic() - self._t0)
            sys.stderr.write(f"\r{frame} {self._message} [{elapsed}s]")
            sys.stderr.flush()
            self._stop.wait(0.1)


DEFAULT_TIMEOUT = 300  # seconds (5 min)


class EngineTimeout(RuntimeError):
    """Raised when the engine subprocess exceeds its timeout."""

    def __init__(self, message: str, partial_stdout: str = "", partial_stderr: str = ""):
        super().__init__(message)
        self.partial_stdout = partial_stdout
        self.partial_stderr = partial_stderr


def _run_cli(cmd: list[str], workdir: Path | None, env: dict,
             label: str, cli_name: str,
             timeout: int | None = DEFAULT_TIMEOUT) -> str:
    with _Spinner(f"{label} is investigating"):
        try:
            result = subprocess.run(
                cmd, cwd=str(workdir) if workdir else None,
                env=env, capture_output=True, text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineTimeout(
                f"{cli_name} timed out after {timeout}s — the cluster may be "
                "unreachable or the agent is stuck. Try --timeout with a "
                "higher value, or check MCP connectivity.",
                partial_stdout=(exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                partial_stderr=(exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            )
    if result.returncode != 0:
        raise RuntimeError(
            f"{cli_name} exited with code {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def gemini_runner(prompt: str, workdir: Path | None = None,
                  timeout: int | None = DEFAULT_TIMEOUT) -> str:
    """Run Gemini CLI non-interactively with the skills dir mounted."""
    env = dict(os.environ)
    env["GEMINI_SKILLS_DIR"] = str(SKILLS_DIR)
    return _run_cli(["gemini", "-p", prompt], workdir, env,
                    label="Gemini", cli_name="gemini CLI",
                    timeout=timeout)


_AGY_CONVERSATIONS_DIR = Path("~/.gemini/antigravity-cli/conversations").expanduser()


def _read_latest_conversation() -> str:
    """Extract assistant text containing STRUCTURED_RESULT from the most recent agy conversation.

    agy stores step payloads as protobuf blobs in SQLite. The readable
    text is embedded within the binary framing and can be recovered with
    decode(errors='replace').
    """
    import sqlite3
    if not _AGY_CONVERSATIONS_DIR.exists():
        return ""
    dbs = sorted(_AGY_CONVERSATIONS_DIR.glob("*.db"),
                 key=lambda p: p.stat().st_mtime, reverse=True)
    if not dbs:
        return ""
    conn = sqlite3.connect(str(dbs[0]))
    try:
        rows = conn.execute(
            "SELECT step_payload FROM steps WHERE step_type = 15 "
            "ORDER BY idx DESC"
        ).fetchall()
    finally:
        conn.close()
    for (blob,) in rows:
        if blob is None:
            continue
        text = blob.decode("utf-8", errors="replace")
        if "STRUCTURED_RESULT" in text:
            return text
    return ""


def antigravity_runner(prompt: str, workdir: Path | None = None,
                       timeout: int | None = DEFAULT_TIMEOUT) -> str:
    """Run the Antigravity CLI (`agy`) non-interactively.

    Uses the isolated MCP config (only the guardrail server) to avoid other
    registered MCP servers hanging agy at startup.  Falls back to reading the
    conversation database when agy's print mode fails to emit stdout.
    """
    from gke_scout.engines import DEFAULT_MCP_CONFIG, write_isolated_mcp_config
    from gke_scout.config import DEFAULT_ENDPOINT, DEFAULT_AUDIT

    shared_cfg = Path(DEFAULT_MCP_CONFIG).expanduser()
    isolated_cfg = write_isolated_mcp_config(DEFAULT_ENDPOINT, DEFAULT_AUDIT)
    backup = None
    if shared_cfg.exists():
        backup = shared_cfg.read_text()

    try:
        Path(isolated_cfg).replace(shared_cfg)
        env = dict(os.environ)
        agy_timeout = f"{(timeout or 900) // 60 + 1}m"
        cmd = ["agy", "--dangerously-skip-permissions",
               "--print-timeout", agy_timeout, "-p", prompt]
        timed_out = False
        try:
            output = _run_cli(cmd, workdir, env,
                              label="Agent", cli_name="antigravity CLI (agy)",
                              timeout=timeout)
        except EngineTimeout:
            output = ""
            timed_out = True

        if output and output.strip():
            return output

        db_text = _read_latest_conversation()
        if db_text:
            return db_text

        if timed_out:
            raise EngineTimeout(
                f"antigravity CLI (agy) timed out after {timeout}s and "
                "produced no usable result. The cluster may be unreachable "
                "or the MCP upstream returned an error. Try --timeout with a "
                "higher value, or check ~/.gemini/antigravity-cli/log/.",
            )
        if not output:
            raise RuntimeError(
                "antigravity CLI (agy) produced no output — this is likely "
                "the agy print mode bug. Check ~/.gemini/antigravity-cli/log/ "
                "for details."
            )
        return output
    finally:
        if backup is not None:
            shared_cfg.write_text(backup)


ENGINES: dict[str, tuple[Callable, bool]] = {
    "antigravity": (antigravity_runner, True),
    "gemini":      (gemini_runner,      False),
}
DEFAULT_ENGINE = "antigravity"


def get_engine(name: str) -> tuple[Callable, bool]:
    """Return (runner, inline_skill) for the named engine."""
    try:
        return ENGINES[name]
    except KeyError:
        raise ValueError(
            f"unknown engine '{name}'; choose from {sorted(ENGINES)}"
        )


def diagnose(workload: str, namespace: str,
             engine: str = DEFAULT_ENGINE,
             workdir: Path | None = None,
             verbose: bool = False,
             timeout: int | None = DEFAULT_TIMEOUT) -> TriageResult:
    runner, inline_skill = get_engine(engine)
    prompt = _build_prompt(workload, namespace, inline_skill=inline_skill)
    try:
        output = runner(prompt, workdir, timeout=timeout)
    except EngineTimeout as exc:
        if verbose and (exc.partial_stdout or exc.partial_stderr):
            sys.stderr.write(f"\n--- partial {engine} output before timeout ---\n")
            if exc.partial_stdout:
                sys.stderr.write(exc.partial_stdout)
            if exc.partial_stderr:
                sys.stderr.write(f"\n--- stderr ---\n{exc.partial_stderr}")
            sys.stderr.write("\n--- end partial output ---\n")
            sys.stderr.flush()
        raise
    if verbose:
        sys.stderr.write(f"\n--- raw {engine} output ({len(output)} chars) ---\n")
        sys.stderr.write(output or "(empty)\n")
        sys.stderr.write("--- end raw output ---\n")
        sys.stderr.flush()
    return parse_structured_result(output)
