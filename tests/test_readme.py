from pathlib import Path


def test_readme_documents_core_usage():
    text = Path("README.md").read_text()
    for token in ["gke-triage", "diagnose", "read-only", "GitOps", "uv", "audit"]:
        assert token in text, f"README missing '{token}'"
