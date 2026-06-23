from gke_triage.models import Finding, TriageResult
from gke_triage.reporter import render_report, write_outputs


def _result():
    return TriageResult(
        root_cause="image tag 'latst' does not exist",
        confidence="high",
        findings=[Finding(
            summary="ImagePullBackOff on payments",
            evidence=["pod payments-1: ImagePullBackOff", "deploy.yaml:12 image: pay:latst"],
        )],
    )


def test_render_report_contains_sections_and_evidence():
    md = render_report("payments", "prod", _result())
    assert "# Triage report: payments" in md
    assert "Root cause" in md
    assert "image tag 'latst'" in md
    assert "ImagePullBackOff on payments" in md
    assert "deploy.yaml:12" in md
    assert "high" in md.lower()


def test_render_report_inconclusive_lists_hypotheses():
    r = TriageResult(root_cause="unclear", confidence="low",
                     findings=[Finding(summary="maybe OOM", evidence=["restarts=5"])])
    md = render_report("ledger", "prod", r)
    assert "Inconclusive" in md
    assert "hypotheses" in md.lower()


def test_write_outputs_writes_report(tmp_path):
    out = write_outputs(tmp_path, "payments", "prod", _result())
    report = (tmp_path / out["report"]).read_text()
    assert "Triage report" in report
    assert "patch" not in out


def test_write_outputs_conclusive_has_no_inconclusive_note(tmp_path):
    out = write_outputs(tmp_path, "payments", "prod", _result())
    report = (tmp_path / out["report"]).read_text()
    assert "Inconclusive" not in report
