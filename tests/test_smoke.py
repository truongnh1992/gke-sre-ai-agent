import gke_triage


def test_package_has_version():
    assert isinstance(gke_triage.__version__, str)
    assert gke_triage.__version__
