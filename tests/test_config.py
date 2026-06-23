import pytest

from gke_triage.config import Config, load_config, DEFAULT_CONFIG_YAML


def test_load_config_from_file(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "gitops_repo: ./gitops\n"
        "upstream_mcp_endpoint: https://container.googleapis.com/mcp\n"
        "audit_log: ~/.gke-triage/audit.jsonl\n"
    )
    cfg = load_config(p)
    assert cfg.gitops_repo == "./gitops"
    assert cfg.upstream_mcp_endpoint.endswith("/mcp")
    assert cfg.audit_log.startswith("/") or ":" in cfg.audit_log


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_defaults_applied_for_omitted_fields(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("gitops_repo: ./g\n")
    cfg = load_config(p)
    assert cfg.upstream_mcp_endpoint
    assert cfg.audit_log


def test_default_yaml_is_valid_template():
    assert "gitops_repo" in DEFAULT_CONFIG_YAML
    assert "upstream_mcp_endpoint" in DEFAULT_CONFIG_YAML
