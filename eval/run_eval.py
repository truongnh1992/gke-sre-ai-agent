"""Check that each broken scenario has the fixtures needed to evaluate gke-triage's
read-only diagnosis (a broken manifest and an expected-fix reference).

Usage: uv run python eval/run_eval.py [--scenario NAME]
Designed for CI / manual runs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCEN = Path(__file__).parent / "scenarios"


def run_scenario(name: str) -> bool:
    d = SCEN / name
    broken, expected = d / "broken.yaml", d / "expected_fix.yaml"
    present = broken.exists() and expected.exists()
    print(f"[scenario] {name}: broken+expected present = {present}")
    return present


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
