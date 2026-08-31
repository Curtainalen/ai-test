from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RequirementReviewCreate(BaseModel):
    requirement_module_id: str
    model_config_id: str | None = None


class RequirementReviewDecision(BaseModel):
    decision: Literal["approved", "rejected"]


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


class RequirementCoverageCreate(BaseModel):
    test_point_id: str
    scenario_type: Literal["api", "ui"]
    scenario_id: str


class ApiScenarioCandidateCreate(BaseModel):
    interface_ids: list[str] = Field(min_length=1, max_length=20)
    requirement_test_point_ids: list[str] = Field(default_factory=list, max_length=100)
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
    requirement_test_point_ids: list[str] = Field(default_factory=list, max_length=100)
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
