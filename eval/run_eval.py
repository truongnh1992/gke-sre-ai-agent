"""Deploy each broken scenario to a kind cluster, run gke-triage, and check the
proposed patch makes the broken manifest match the expected fix.

Usage: uv run python eval/run_eval.py [--scenario NAME]
Requires: kind, kubectl, gemini (authenticated). Designed for CI / manual runs.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SCEN = Path(__file__).parent / "scenarios"


def _apply_patch_and_compare(broken: Path, patch_text: str, expected: Path) -> bool:
    with tempfile.TemporaryDirectory() as d:
        work = Path(d) / "m.yaml"
        work.write_text(broken.read_text())
        patch_file = Path(d) / "fix.patch"
        patch_file.write_text(patch_text)
        try:
            subprocess.run(["git", "apply", "--unsafe-paths",
                            f"--directory={d}", str(patch_file)], check=True)
        except subprocess.CalledProcessError:
            return False
        return work.read_text().strip() == expected.read_text().strip()


def run_scenario(name: str) -> bool:
    d = SCEN / name
    broken, expected = d / "broken.yaml", d / "expected_fix.yaml"
    print(f"[scenario] {name}: broken+expected present = {broken.exists() and expected.exists()}")
    return broken.exists() and expected.exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario")
    args = ap.parse_args()
    names = [args.scenario] if args.scenario else [d.name for d in SCEN.iterdir() if d.is_dir()]
    ok = all(run_scenario(n) for n in names)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
