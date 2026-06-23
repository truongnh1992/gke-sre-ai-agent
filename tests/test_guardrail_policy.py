import pytest

from gke_scout.guardrail.policy import evaluate
from gke_scout.models import ToolCall


@pytest.mark.parametrize("name", [
    "list_pods", "get_pod", "get_logs", "list_events",
    "describe_deployment", "read_configmap",
])
def test_read_only_calls_allowed(name):
    d = evaluate(ToolCall(name=name, args={}))
    assert d.allowed is True


@pytest.mark.parametrize("name", [
    "apply_manifest", "delete_pod", "patch_deployment",
    "scale_deployment", "create_namespace", "exec_command",
])
def test_mutating_calls_blocked(name):
    d = evaluate(ToolCall(name=name, args={}))
    assert d.allowed is False
    assert name.split("_")[0] in d.reason.lower()


def test_unknown_verb_blocked_by_default():
    d = evaluate(ToolCall(name="frobnicate_cluster", args={}))
    assert d.allowed is False
    assert "default-deny" in d.reason.lower()


def test_exec_blocked_even_if_named_get():
    d = evaluate(ToolCall(name="get_exec_session", args={}))
    assert d.allowed is False


@pytest.mark.parametrize("name", ["deletePod", "delete-pod", "delete.pod", "scaleDeployment", "applyManifest"])
def test_camelcase_and_hyphen_mutations_blocked_as_mutating(name):
    d = evaluate(ToolCall(name=name, args={}))
    assert d.allowed is False
    assert "mutating" in d.reason.lower()


@pytest.mark.parametrize("name", ["listPods", "getPod", "describe-deployment"])
def test_camelcase_reads_allowed(name):
    assert evaluate(ToolCall(name=name, args={})).allowed is True
