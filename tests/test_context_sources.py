from gke_triage.context.sources import find_manifest_for_workload


def _write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_finds_deployment_by_metadata_name(tmp_path):
    _write(tmp_path / "apps/payments/deploy.yaml",
           "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: payments\n")
    _write(tmp_path / "apps/other/deploy.yaml",
           "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: ledger\n")
    hit = find_manifest_for_workload(tmp_path, "payments")
    assert hit is not None
    assert hit.endswith("apps/payments/deploy.yaml")


def test_returns_none_when_absent(tmp_path):
    _write(tmp_path / "a.yaml", "kind: Deployment\nmetadata:\n  name: foo\n")
    assert find_manifest_for_workload(tmp_path, "missing") is None


def test_handles_multi_doc_yaml(tmp_path):
    _write(tmp_path / "bundle.yaml",
           "kind: Service\nmetadata:\n  name: payments\n---\n"
           "kind: Deployment\nmetadata:\n  name: payments\n")
    hit = find_manifest_for_workload(tmp_path, "payments")
    assert hit.endswith("bundle.yaml")
