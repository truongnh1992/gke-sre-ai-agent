from gke_scout.guardrail.redact import redact


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


def test_redacts_bearer_with_base64_chars():
    out = redact("Authorization: Bearer eyJ0eXAi+OiJKV1/QiLCJhbGc=")
    assert "eyJ0eXAi" not in out
    assert "REDACTED" in out


def test_redacts_sensitive_kv_inside_text_leaf():
    # Secret serialized as YAML text inside an MCP content block
    payload = {"content": [{"type": "text",
               "text": "kind: Secret\ndata:\n  password: c2VjcmV0Cg==\n  host: db\n"}]}
    out = redact(payload)
    blob = out["content"][0]["text"]
    assert "c2VjcmV0Cg==" not in blob
    assert "REDACTED" in blob
    assert "host: db" in blob  # non-sensitive line preserved


def test_redacts_kv_in_plain_string():
    assert "hunter2" not in redact("db_password=hunter2")
    assert "REDACTED" in redact("api_key: AKIA12345")


def test_text_redaction_preserves_nonsensitive():
    assert redact("replicas: 3") == "replicas: 3"
