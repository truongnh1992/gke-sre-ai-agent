from gke_triage.guardrail.redact import redact


def test_redacts_secret_kind_data_values():
    payload = {
        "kind": "Secret",
        "data": {"password": "c2VjcmV0", "token": "YWJj"},
    }
    out = redact(payload)
    assert out["data"]["password"] == "***REDACTED***"
    assert out["data"]["token"] == "***REDACTED***"


def test_redacts_sensitive_keys_anywhere():
    payload = {"env": [{"name": "API_KEY", "value": "supersecret"}]}
    out = redact(payload)
    assert out["env"][0]["value"] == "***REDACTED***"
    payload2 = {"env": [{"name": "LOG_LEVEL", "value": "debug"}]}
    assert redact(payload2)["env"][0]["value"] == "debug"


def test_redacts_by_sensitive_key_name():
    payload = {"config": {"db_password": "hunter2", "host": "db.local"}}
    out = redact(payload)
    assert out["config"]["db_password"] == "***REDACTED***"
    assert out["config"]["host"] == "db.local"


def test_does_not_mutate_input():
    payload = {"config": {"password": "x"}}
    redact(payload)
    assert payload["config"]["password"] == "x"


def test_redacts_in_strings_via_regex():
    text = 'output: Authorization: Bearer abcdef123456789'
    out = redact(text)
    assert "abcdef123456789" not in out
    assert "REDACTED" in out
