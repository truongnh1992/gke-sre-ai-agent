from gke_triage.models import Finding, TriageResult
from gke_triage.reporter import render_report, write_outputs


def _result():
    return TriageResult(
        root_cause="image tag 'latst' does not exist",
        confidence="high",
        findings=[Finding(
            summary="ImagePullBackOff on payments",
            evidence=["pod payments-1: ImagePullBackOff", "deploy.yaml:12 image: pay:latst"],
            manifest_path="apps/payments/deploy.yaml",
        )],
        proposed_patch="--- a/apps/payments/deploy.yaml\n+++ b/apps/payments/deploy.yaml\n",
    )


def test_render_report_contains_sections_and_evidence():
    md = render_report("payments", "prod", _result())
    assert "# Triage report: payments" in md
    assert "Root cause" in md
    assert "image tag 'latst'" in md
    assert "ImagePullBackOff on payments" in md
    assert "deploy.yaml:12" in md
    assert "high" in md.lower()


def test_render_report_inconclusive_lists_hypotheses_no_fix():
    r = TriageResult(root_cause="unclear", confidence="low",
                     findings=[Finding(summary="maybe OOM", evidence=["restarts=5"])],
                     proposed_patch=None)
    md = render_report("ledger", "prod", r)
    assert "Inconclusive" in md or "hypothes" in md.lower()
    assert "No automated fix" in md


def test_write_outputs_writes_report_and_patch(tmp_path):
    out = write_outputs(tmp_path, "payments", "prod", _result(), open_pr=False)
    report = (tmp_path / out["report"]).read_text()
    patch = (tmp_path / out["patch"]).read_text()
    assert "Triage report" in report
    assert patch.startswith("--- a/")
    assert out["pr_url"] is None


def test_write_outputs_skips_patch_when_no_fix(tmp_path):
    r = TriageResult(root_cause="x", confidence="low", findings=[], proposed_patch=None)
    out = write_outputs(tmp_path, "x", "prod", r, open_pr=False)
    assert out["patch"] is None
