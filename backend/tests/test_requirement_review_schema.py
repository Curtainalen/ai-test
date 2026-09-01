from app.schemas.ai import RequirementReviewPayload


def test_requirement_review_payload_accepts_structured_quality_report():
    payload = RequirementReviewPayload.model_validate({
        "test_points": [{"stable_key": "login.valid", "title": "正确登录", "expected_result": "进入工作台", "risk": "medium"}],
        "summary": "登录需求可测，但失败路径缺少锁定规则。",
        "scores": {"clarity": 75, "completeness": 80, "consistency": 90, "testability": 70, "feasibility": 95, "logic": 80},
        "issues": [{"type": "testability", "priority": "high", "title": "失败规则缺失", "description": "未定义密码连续错误后的行为", "suggestion": "补充锁定阈值和解除条件"}],
    })

    assert payload.scores["testability"] == 70
    assert payload.issues[0].priority == "high"
