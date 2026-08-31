import os, pytest
from app.errors import AppError
from app.services.masking import mask_data, mask_url
from app.services.request_engine import compose_request, evaluate_assertions

def test_compose_supports_new_and_legacy_variables_and_masks():
    os.environ["AITEST_SECRET_LOGIN_PASSWORD"] = "real-password"
    result = compose_request({"method":"POST","url":"/login?token=${token}","headers":{"X-Legacy":"{{legacy}}"},"body":{"password":"secret://login_password"},"variables":{"legacy":"ok"}}, {"base_url":"https://example.test","variables":{"token":"abc"},"global_headers":{}})
    assert result["request"]["headers"]["X-Legacy"] == "ok"
    assert result["request"]["body"]["password"] == "real-password"
    assert "abc" not in result["preview"]["url"]
    assert result["preview"]["body"]["password"] == "******"

def test_missing_variable_has_name_and_path():
    with pytest.raises(AppError) as caught: compose_request({"url":"/users/${user_id}","headers":{}}, {"base_url":"https://example.test"})
    assert caught.value.code == "VARIABLE_MISSING"; assert caught.value.details["variables"][0] == {"name":"user_id","paths":["request.url"]}

def test_assertions_and_masking():
    results = evaluate_assertions({"status_code":200,"headers":{"x-id":"1"},"json":{"data":{"ok":True}},"text":"hello"}, [{"type":"status_code","expected":200},{"type":"json_field","field":"data.ok","expected":True},{"type":"text_contains","expected":"ell"}])
    assert all(item["passed"] for item in results)
    assert mask_data({"Authorization":"Bearer x","nested":{"password":"x"}}) == {"Authorization":"******","nested":{"password":"******"}}
    assert "abc" not in mask_url("https://x.test/a?access_token=abc")

def test_path_params_scope_priority_and_target_origin():
    result = compose_request({"url":"/users/{id}","path_params":{"id":"${id}"},"variables":{"id":"interface"},"headers":{}}, {"base_url":"https://example.test","variables":{"id":"environment"}}, [{"id":"case"},{"id":"step"}])
    assert result["request"]["url"] == "https://example.test/users/step"
    with pytest.raises(AppError) as caught:
        compose_request({"url":"https://evil.test/a","headers":{}}, {"base_url":"https://example.test"})
    assert caught.value.code == "TARGET_URL_FORBIDDEN"

def test_cookies_and_secret_echo_values_are_fully_masked():
    os.environ["AITEST_SECRET_API_TOKEN"] = "top-secret-value"
    result = compose_request({"url":"/echo","headers":{"X-Trace":"secret://api_token"},"cookies":{"session":"plain-cookie"}}, {"base_url":"https://example.test"})
    assert result["preview"]["cookies"] == "******"
    assert result["preview"]["headers"]["X-Trace"] == "******"
