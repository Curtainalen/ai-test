from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RequirementReviewCreate(BaseModel):
    requirement_module_id: str
    model_config_id: str | None = None


class RequirementReviewDecision(BaseModel):
    decision: Literal["approved", "rejected"]


class RequirementReviewIssuePayload(BaseModel):
    type: Literal["clarity", "completeness", "consistency", "testability", "feasibility", "logic"]
    priority: Literal["low", "medium", "high"]
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    suggestion: str = Field(default="", max_length=5000)


class RequirementTestPointPayload(BaseModel):
    stable_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str = Field(min_length=1, max_length=255)
    preconditions: list[str] = Field(default_factory=list, max_length=50)
    test_data_refs: list[str] = Field(default_factory=list, max_length=50)
    expected_result: str = Field(min_length=1, max_length=5000)
    risk: Literal["low", "medium", "high"]

    @field_validator("test_data_refs")
    @classmethod
    def secret_refs_only(cls, values: list[str]) -> list[str]:
        if any(value and not value.startswith("secret://") for value in values):
            raise ValueError("测试数据只能使用 secret:// 引用")
        return values


class RequirementReviewPayload(BaseModel):
    test_points: list[RequirementTestPointPayload] = Field(min_length=1, max_length=100)
    ambiguities: list[str] = Field(default_factory=list, max_length=100)
    acceptance_suggestions: list[str] = Field(default_factory=list, max_length=100)
    summary: str = Field(default="", max_length=10000)
    recommendations: list[str] = Field(default_factory=list, max_length=100)
    # Providers may add useful dimensions such as coverage or security; retain them
    # while keeping values bounded and numeric.
    scores: dict[str, int | str] = Field(default_factory=dict, max_length=30)
    issues: list[RequirementReviewIssuePayload] = Field(default_factory=list, max_length=200)

    @field_validator("scores")
    @classmethod
    def score_range(cls, values: dict[str, int]) -> dict[str, int]:
        for value in values.values():
            if isinstance(value, bool):
                raise ValueError("评审评分格式无效")
            if isinstance(value, int) and not 0 <= value <= 100:
                raise ValueError("评审评分必须在 0 到 100 之间")
            if isinstance(value, str) and value not in {"low", "medium", "high"}:
                raise ValueError("评审等级必须是 low、medium 或 high")
        return values


class RequirementCoverageCreate(BaseModel):
    test_point_id: str
    scenario_type: Literal["api", "ui"]
    scenario_id: str


class RequirementTestCaseGenerate(BaseModel):
    # 新流程直接从已确认模块生成；review_id 仅为历史客户端保留。
    requirement_module_id: str | None = None
    review_id: str | None = None
    model_config_id: str | None = None
    case_types: list[Literal["normal", "abnormal", "boundary", "permission", "security", "compatibility"]] = Field(
        default_factory=lambda: ["normal", "abnormal", "boundary", "permission", "security", "compatibility"],
        min_length=1,
        max_length=6,
    )
    priority_strategy: Literal["risk_based", "all_high", "all_medium"] = "risk_based"

    @field_validator("case_types")
    @classmethod
    def case_types_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("测试用例类型不能重复")
        return values

    @model_validator(mode="after")
    def require_generation_source(self):
        if bool(self.requirement_module_id) == bool(self.review_id):
            raise ValueError("测试用例生成必须且只能指定需求模块或历史评审")
        return self


class RequirementTestCaseDecision(BaseModel):
    decision: Literal["confirmed", "rejected"]
    revision: int = Field(ge=1)


class RequirementTestCaseStepPayload(BaseModel):
    seq: int = Field(ge=1, le=1000)
    action: str = Field(min_length=1, max_length=1000)
    expected_result: str = Field(min_length=1, max_length=5000)


class RequirementTestCasePayload(BaseModel):
    stable_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str = Field(min_length=1, max_length=255)
    case_type: Literal["normal", "exception", "boundary", "permission", "consistency"]
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    preconditions: list[str] = Field(default_factory=list, max_length=50)
    test_data_refs: list[str] = Field(default_factory=list, max_length=50)
    steps: list[RequirementTestCaseStepPayload] = Field(min_length=1, max_length=100)
    expected_result: str = Field(min_length=1, max_length=5000)

    @field_validator("test_data_refs")
    @classmethod
    def test_case_secret_refs_only(cls, values: list[str]) -> list[str]:
        if any(value and not value.startswith("secret://") for value in values):
            raise ValueError("测试数据只能使用 secret:// 引用")
        return values


class RequirementTestCaseBatchPayload(BaseModel):
    cases: list[RequirementTestCasePayload] = Field(min_length=1, max_length=100)


class ApiScenarioCandidateCreate(BaseModel):
    interface_ids: list[str] = Field(min_length=1, max_length=20)
    requirement_test_case_ids: list[str] = Field(min_length=1, max_length=100)
    instruction: str = Field(min_length=1, max_length=4000)
    model_config_id: str | None = None


class ApiCandidateAssertion(BaseModel):
    type: Literal["status_code", "header", "json_field", "text_contains"]
    field: str | None = Field(default=None, max_length=512)
    expected: str | int | float | bool


class ApiCandidateStep(BaseModel):
    seq: int = Field(ge=1, le=1000)
    name: str = Field(min_length=1, max_length=255)
    interface_id: str
    expected_result: str = Field(min_length=1, max_length=5000)
    assertions: list[ApiCandidateAssertion] = Field(min_length=1, max_length=50)
    test_data_refs: list[str] = Field(default_factory=list, max_length=50)
    timeout_ms: int = Field(default=30000, ge=100, le=300000)

    @field_validator("test_data_refs")
    @classmethod
    def validate_test_data_refs(cls, values: list[str]) -> list[str]:
        if any(not value.startswith("secret://") for value in values):
            raise ValueError("API 候选测试数据只能使用 secret:// 引用")
        return values


class ApiScenarioProposal(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    requirement_test_case_ids: list[str] = Field(min_length=1, max_length=100)
    steps: list[ApiCandidateStep] = Field(min_length=1, max_length=200)

    @field_validator("steps")
    @classmethod
    def validate_step_sequence(cls, steps: list[ApiCandidateStep]) -> list[ApiCandidateStep]:
        if len({item.seq for item in steps}) != len(steps):
            raise ValueError("API 候选步骤序号不能重复")
        return steps


class ApiScenarioCandidateDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=2000)


class ApiScenarioCandidateMaterialize(BaseModel):
    revision: int = Field(ge=1)
