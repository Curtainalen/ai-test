from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

LOCATOR_TYPES = ("test_id", "data_testid", "id", "role", "label", "placeholder", "name", "css", "xpath")


class LocatorSpec(BaseModel):
    type: Literal["test_id", "data_testid", "id", "role", "label", "placeholder", "name", "css", "xpath"]
    value: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=512)
    exact: bool = False

    @field_validator("value", "name")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 for char in value):
            raise ValueError("定位器不能包含控制字符")
        return value


class PageScoped(BaseModel):
    module_id: str


class UiModuleCreate(BaseModel):
    parent_id: str | None = None
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=10000)


class UiModuleUpdate(UiModuleCreate):
    revision: int = Field(ge=1)


class UiPageCreate(BaseModel):
    module_id: str
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    description: str = Field(default="", max_length=10000)


class UiPageUpdate(UiPageCreate):
    revision: int = Field(ge=1)


class UiElementCreate(BaseModel):
    page_id: str
    name: str = Field(min_length=1, max_length=255)
    primary_locator: LocatorSpec
    fallback_locators: list[LocatorSpec] = Field(default_factory=list, max_length=8)
    locator_index: int | None = Field(default=None, ge=0, le=100)
    iframe_locator: LocatorSpec | None = None
    description: str = Field(default="", max_length=10000)


class UiElementUpdate(UiElementCreate):
    revision: int = Field(ge=1)


class UiPageStepCreate(BaseModel):
    page_id: str
    module_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)


class UiPageStepUpdate(UiPageStepCreate):
    revision: int = Field(ge=1)


class UiPageStepDetailCreate(BaseModel):
    step_sort: int = Field(ge=1, le=10000)
    step_type: Literal["action", "assertion", "wait"]
    element_id: str | None = None
    operation: Literal["navigate", "click", "fill", "select", "hover", "press", "check", "uncheck", "visible", "text", "url", "wait_for"]
    input_value: dict[str, Any] | None = None
    assertion: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def validate_operation(self):
        element_operations = {"click", "fill", "select", "hover", "press", "check", "uncheck", "visible", "text"}
        if self.operation in element_operations and not self.element_id:
            raise ValueError("元素操作必须指定 element_id")
        if self.operation == "navigate" and self.element_id:
            raise ValueError("navigate 操作不能指定 element_id")
        if self.input_value and any("password" in str(key).lower() for key in self.input_value):
            values = [value for key, value in self.input_value.items() if "password" in str(key).lower()]
            if any(isinstance(value, str) and not value.startswith("secret://") for value in values):
                raise ValueError("敏感输入必须使用 secret:// 引用")
        return self


class UiPageStepDetailUpdate(UiPageStepDetailCreate):
    pass


class UiScenarioStepIn(BaseModel):
    page_step_id: str
    step_sort: int = Field(ge=1, le=10000)
    data_override: dict[str, Any] = Field(default_factory=dict)


class UiScenarioCreate(BaseModel):
    module_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    status: Literal["draft", "confirmed", "archived"] = "draft"
    steps: list[UiScenarioStepIn] = Field(default_factory=list, max_length=1000)


class UiScenarioUpdate(UiScenarioCreate):
    revision: int = Field(ge=1)


class UiVerifyRequest(BaseModel):
    environment_id: str
    target_url: str | None = Field(default=None, max_length=2048)
    navigation_timeout_ms: int = Field(default=15000, ge=100, le=60000)
    operation_timeout_ms: int = Field(default=5000, ge=100, le=30000)
    total_timeout_ms: int = Field(default=30000, ge=100, le=120000)


class UiPageLocatorVerifyRequest(UiVerifyRequest):
    locator: LocatorSpec
    iframe_locator: LocatorSpec | None = None


class UiListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = Field(default=None, max_length=255)


SAFE_UI_OPERATIONS = ("navigate", "click", "fill", "select", "hover", "press", "check", "uncheck", "wait_for", "assert_url", "assert_visible", "assert_text")
SIDE_EFFECT_UI_OPERATIONS = ("click", "check", "uncheck", "press", "select")


class UiActionSpec(BaseModel):
    operation: Literal["navigate", "click", "fill", "select", "hover", "press", "check", "uncheck", "wait_for", "assert_url", "assert_visible", "assert_text"]
    locator: LocatorSpec | None = None
    value: str | None = Field(default=None, max_length=4096)
    timeout_ms: int = Field(default=5000, ge=100, le=60000)

    @model_validator(mode="after")
    def validate_action(self):
        element_operations = {"click", "fill", "select", "hover", "press", "check", "uncheck", "assert_visible", "assert_text"}
        if self.operation in element_operations and self.locator is None:
            raise ValueError("元素动作必须提供定位器")
        if self.operation == "navigate" and not self.value:
            raise ValueError("navigate 动作必须提供目标路径")
        if self.operation == "fill" and self.value is not None and any(word in self.value.lower() for word in ("password=", "token=", "secret=")) and not self.value.startswith("secret://"):
            raise ValueError("敏感输入必须使用 secret:// 引用")
        return self


class UiExplorationCreate(BaseModel):
    environment_id: str
    goal: str = Field(min_length=1, max_length=4000)
    requirement_test_point_ids: list[str] = Field(default_factory=list, max_length=100)
    start_url: str = Field(min_length=1, max_length=2048)
    allowed_paths: list[str] = Field(default_factory=list, max_length=100)
    allowed_operations: list[Literal["navigate", "click", "fill", "select", "hover", "press", "check", "uncheck", "wait_for", "assert_url", "assert_visible", "assert_text"]] = Field(default_factory=lambda: ["navigate", "click", "fill", "select", "hover", "press", "check", "uncheck", "wait_for", "assert_url", "assert_visible", "assert_text"])
    blocked_operations: list[str] = Field(default_factory=lambda: ["evaluate", "upload", "download", "new_page"])
    max_steps: int = Field(default=5, ge=1, le=50)
    total_timeout_ms: int = Field(default=60000, ge=1000, le=300000)
    navigation_timeout_ms: int = Field(default=30000, ge=1000, le=60000)
    operation_timeout_ms: int = Field(default=8000, ge=500, le=30000)
    llm_turn_timeout_ms: int = Field(default=45000, ge=1000, le=60000)
    actions: list[UiActionSpec] = Field(default_factory=list, max_length=50)

    @field_validator("allowed_paths")
    @classmethod
    def validate_allowed_paths(cls, value: list[str]) -> list[str]:
        if any(not item.startswith("/") or "//" in item or "\\" in item for item in value):
            raise ValueError("允许页面范围必须是以 / 开始的相对路径")
        return value

    @model_validator(mode="after")
    def validate_actions(self):
        if len(self.actions) > self.max_steps:
            raise ValueError("初始动作不能超过最大探索步数")
        allowed = set(self.allowed_operations)
        if any(action.operation not in allowed for action in self.actions):
            raise ValueError("初始动作包含未授权操作")
        if self.navigation_timeout_ms > self.total_timeout_ms or self.operation_timeout_ms > self.total_timeout_ms or self.llm_turn_timeout_ms > self.total_timeout_ms:
            raise ValueError("阶段超时不能大于探索总超时")
        return self


class UiExplorationActionRequest(BaseModel):
    action: UiActionSpec


class UiExplorationApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]


class UiAiAction(BaseModel):
    operation: Literal["navigate", "click", "fill", "select", "hover", "press", "check", "uncheck", "wait_for", "assert_url", "assert_visible", "assert_text"]
    target_element_key: str | None = Field(default=None, max_length=160)
    value: str | None = Field(default=None, max_length=4096)
    reason: str = Field(min_length=1, max_length=1000)
    expected: str = Field(min_length=1, max_length=1000)


class UiExecutionCreate(BaseModel):
    environment_id: str


class UiCandidateGenerateRequest(BaseModel):
    candidate_type: Literal["automation_bundle", "locator", "scenario", "repair", "exploration_plan"]
    exploration_id: str | None = None
    execution_id: str | None = None
    instruction: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_source(self):
        if self.candidate_type in {"automation_bundle", "locator", "exploration_plan"} and not self.exploration_id:
            raise ValueError("定位器或探索候选必须关联探索会话")
        if self.candidate_type == "repair" and not self.execution_id:
            raise ValueError("修复候选必须关联执行任务")
        return self


class UiCandidateReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=2000)


class UiBundlePage(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    description: str = Field(default="", max_length=10000)


class UiBundleElement(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    page_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    primary_locator: LocatorSpec
    fallback_locators: list[LocatorSpec] = Field(default_factory=list, max_length=8)
    iframe_locator: LocatorSpec | None = None
    description: str = Field(default="", max_length=10000)


class UiBundleStepDetail(BaseModel):
    step_sort: int = Field(ge=1, le=1000)
    step_type: Literal["action", "assertion", "wait"]
    operation: Literal["navigate", "click", "fill", "select", "hover", "press", "check", "uncheck", "visible", "text", "url", "wait_for"]
    element_key: str | None = Field(default=None, max_length=64)
    input_value: dict[str, Any] | None = None
    assertion: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def validate_detail(self):
        element_operations = {"click", "fill", "select", "hover", "press", "check", "uncheck", "visible", "text"}
        if self.operation in element_operations and not self.element_key:
            raise ValueError("元素操作必须关联候选元素")
        if self.operation == "navigate" and self.element_key:
            raise ValueError("navigate 操作不能关联候选元素")
        if self.input_value:
            for key, value in self.input_value.items():
                if any(word in str(key).lower() for word in ("password", "token", "secret")) and isinstance(value, str) and not value.startswith("secret://"):
                    raise ValueError("敏感输入必须使用 secret:// 引用")
        return self


class UiBundlePageStep(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    page_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    details: list[UiBundleStepDetail] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_order(self):
        if len({item.step_sort for item in self.details}) != len(self.details):
            raise ValueError("页面步骤详情序号不能重复")
        return self


class UiAutomationBundle(BaseModel):
    module_name: str = Field(min_length=1, max_length=128)
    module_description: str = Field(default="", max_length=10000)
    pages: list[UiBundlePage] = Field(min_length=1, max_length=30)
    elements: list[UiBundleElement] = Field(default_factory=list, max_length=300)
    page_steps: list[UiBundlePageStep] = Field(min_length=1, max_length=200)
    scenario_name: str = Field(min_length=1, max_length=255)
    scenario_description: str = Field(default="", max_length=10000)
    scenario_step_keys: list[str] = Field(min_length=1, max_length=200)
    requirement_test_point_ids: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_references(self):
        page_keys = {item.key for item in self.pages}
        element_keys = {item.key for item in self.elements}
        step_keys = {item.key for item in self.page_steps}
        if len(page_keys) != len(self.pages) or len(element_keys) != len(self.elements) or len(step_keys) != len(self.page_steps):
            raise ValueError("候选 key 不能重复")
        if any(item.page_key not in page_keys for item in self.elements):
            raise ValueError("元素引用了不存在的候选页面")
        for step in self.page_steps:
            if step.page_key not in page_keys or any(detail.element_key and detail.element_key not in element_keys for detail in step.details):
                raise ValueError("页面步骤引用了不存在的候选资产")
            if any(detail.element_key and next(item for item in self.elements if item.key == detail.element_key).page_key != step.page_key for detail in step.details):
                raise ValueError("页面步骤只能引用同一页面的候选元素")
        if len(set(self.scenario_step_keys)) != len(self.scenario_step_keys) or any(key not in step_keys for key in self.scenario_step_keys):
            raise ValueError("场景引用了不存在或重复的候选页面步骤")
        return self


class UiCandidateConfirmBundleRequest(BaseModel):
    pass


class UiRepairSuggestion(BaseModel):
    locator: LocatorSpec
    evidence: str = Field(min_length=1, max_length=2000)


class UiRepairProposal(BaseModel):
    category: Literal["PRODUCT_DEFECT", "LOCATOR_BROKEN", "PAGE_LOAD_ERROR", "AUTH_FAILED", "TEST_DATA_ERROR", "ENVIRONMENT_ERROR", "ACTUATOR_ERROR", "EXPECTATION_MISMATCH"]
    suggestions: list[UiRepairSuggestion] = Field(default_factory=list, max_length=20)
