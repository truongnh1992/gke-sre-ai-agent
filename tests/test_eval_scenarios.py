from pathlib import Path

import yaml

SCEN = Path(__file__).parent.parent / "eval" / "scenarios"


def test_each_scenario_has_broken_and_fix():
    scenarios = [d for d in SCEN.iterdir() if d.is_dir()]
    assert len(scenarios) >= 2
    for d in scenarios:
        assert (d / "broken.yaml").exists(), f"{d} missing broken.yaml"
        assert (d / "expected_fix.yaml").exists(), f"{d} missing expected_fix.yaml"


def test_broken_and_fix_differ_and_are_valid_yaml():
    for d in [x for x in SCEN.iterdir() if x.is_dir()]:
        broken = (d / "broken.yaml").read_text()
        fixed = (d / "expected_fix.yaml").read_text()
        assert broken != fixed, f"{d}: broken and fix identical"
        list(yaml.safe_load_all(broken))
        list(yaml.safe_load_all(fixed))
