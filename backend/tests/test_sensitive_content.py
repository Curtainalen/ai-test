from app.services.sensitive import contains_suspected_secret, sanitize_block, sanitize_text


def test_sanitize_text_replaces_credentials_with_references():
    original = "账号：admin\n密码：Abc123456\nToken: token-value-123456"

    sanitized, spans, items = sanitize_text(original)

    assert "Abc123456" not in sanitized
    assert "token-value-123456" not in sanitized
    assert "[data://login_username]" in sanitized
    assert "[secret://login_password]" in sanitized
    assert "[secret://access_token]" in sanitized
    assert {item["reference"] for item in items} == {
        "data://login_username", "secret://login_password", "secret://access_token",
    }
    assert all("value" not in span for span in spans)


def test_password_rule_is_not_treated_as_a_real_credential():
    sanitized, spans, items = sanitize_text("密码至少 8 位，且必须包含数字")

    assert sanitized == "密码至少 8 位，且必须包含数字"
    assert spans == []
    assert items == []


def test_manual_correction_accepts_references_but_rejects_real_values():
    # 人工校正应能保留引用；若写入真实值，服务层会用同一检测器拒绝保存。
    assert not contains_suspected_secret("登录密码：[secret://login_password]")
    assert contains_suspected_secret("登录密码：Abc123456")
    assert not contains_suspected_secret("密码至少 8 位，且必须包含数字")
    assert not contains_suspected_secret("password=******")


def test_sanitize_block_also_removes_credentials_from_structured_content():
    block, items = sanitize_block({
        "seq": 3,
        "content": "API Key: key-value-123456",
        "structured_content": {"headers": ["API Key"], "rows": [["key-value-123456"]]},
    })

    assert "key-value-123456" not in block["content"]
    assert "key-value-123456" not in str(block["structured_content"])
    assert items[0]["reference"] == "secret://api_key"


def test_json_credentials_are_sanitized_and_rejected_when_plaintext():
    sanitized, _, items = sanitize_text('{"username":"tester","password":"json-secret-123"}')

    assert "json-secret-123" not in sanitized
    assert "[secret://login_password]" in sanitized
    assert {item["reference"] for item in items} == {"data://login_username", "secret://login_password"}
    assert contains_suspected_secret('{"password":"json-secret-123"}')
    assert not contains_suspected_secret('{"password":"secret://login_password"}')
