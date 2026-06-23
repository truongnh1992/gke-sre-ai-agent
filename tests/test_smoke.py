import gke_scout


def test_package_has_version():
    assert isinstance(gke_scout.__version__, str)
    assert gke_scout.__version__
