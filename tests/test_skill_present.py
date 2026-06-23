from pathlib import Path

import gke_scout


def test_skill_md_exists_and_has_required_sections():
    root = Path(gke_scout.__file__).parent
    skill = root / "skills" / "k8s-troubleshooter" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text()
    assert text.startswith("---")
    assert "name:" in text
    assert "ImagePullBackOff" in text
    assert "OOMKilled" in text
    assert "STRUCTURED_RESULT" in text
