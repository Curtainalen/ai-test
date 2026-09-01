from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class OpenApiImportAuth(BaseModel):
    type: Literal["none", "basic", "bearer", "header"] = "none"
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=2048)
    token: str | None = Field(default=None, max_length=8192)
    header_name: str | None = Field(default=None, max_length=255)
    header_value: str | None = Field(default=None, max_length=8192)

    @model_validator(mode="after")
    def validate_credentials(self):
        if self.type == "basic" and (not self.username or self.password is None):
            raise ValueError("Basic 鉴权需要用户名和密码")
        if self.type == "bearer" and not self.token:
            raise ValueError("Bearer 鉴权需要 Token")
        if self.type == "header" and (not self.header_name or self.header_value is None):
            raise ValueError("自定义 Header 鉴权需要名称和值")
        for value in (self.username, self.password, self.token, self.header_name, self.header_value):
            if value and ("\r" in value or "\n" in value):
                raise ValueError("鉴权字段不能包含换行符")
        if self.type == "header" and self.header_name.lower() in {"host", "content-length", "transfer-encoding"}:
            raise ValueError("不能覆盖受保护的请求 Header")
        return self


class OpenApiUrlImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    auth: OpenApiImportAuth = Field(default_factory=OpenApiImportAuth)


class ApiImportConfirmRequest(BaseModel):
    selected_stable_keys: list[str] | None = Field(default=None, max_length=10000)

class RequirementModuleUpdate(BaseModel):
    name: str = Field(min_length=1,max_length=255); description: str = Field(default="",max_length=10000); source_block_ids: list[str] = Field(default_factory=list, max_length=10000); source_type: Literal["content_blocks", "manual"] = "content_blocks"; revision: int = Field(ge=1)

class ContentBlockUpdate(BaseModel):
    content: str = Field(max_length=100000)

class RequirementModuleCreate(BaseModel):
    document_version_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    source_block_ids: list[str] = Field(default_factory=list, max_length=10000)
    source_type: Literal["content_blocks", "manual"] = "content_blocks"

class RequirementModuleSplitRequest(BaseModel):
    method: Literal["heading", "rule", "ai"] = "rule"
    document_version_id: str
    heading_level: int | None = Field(default=None, ge=1, le=6)

class RequirementModuleConfirmRequest(BaseModel):
    revision: int = Field(ge=1)

class RequirementModulesConfirmRequest(BaseModel):
    document_version_id: str
    revisions: dict[str, int] = Field(default_factory=dict)

class RequirementModuleSplitExistingRequest(BaseModel):
    revision: int = Field(ge=1)
    modules: list[RequirementModuleCreate] = Field(min_length=2, max_length=100)

class RequirementModuleMergeRequest(BaseModel):
    module_ids: list[str] = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    revision_by_id: dict[str, int] = Field(default_factory=dict)

class RequirementModuleReorderRequest(BaseModel):
    module_ids: list[str] = Field(min_length=1, max_length=1000)
    revisions: dict[str, int] = Field(default_factory=dict)

class RequestModel(BaseModel):
    method: str = "GET"; url: str; path_params: dict[str,Any] = Field(default_factory=dict); params: dict[str,Any] = Field(default_factory=dict); headers: dict[str,Any] = Field(default_factory=dict); cookies: dict[str,Any] = Field(default_factory=dict)
    body_type: Literal["none","json","raw","urlencoded","form-data","binary"] = "none"; body: Any = None; auth: dict[str,Any] = Field(default_factory=dict); variables: dict[str,Any] = Field(default_factory=dict); extracts: list[dict] = Field(default_factory=list); assertions: list[dict] = Field(default_factory=list)

class PreviewRequest(BaseModel):
    environment_id: str; interface_id: str | None = None; request: RequestModel | None = None; request_override: dict = Field(default_factory=dict); case_variables: dict = Field(default_factory=dict); step_variables: dict = Field(default_factory=dict)

class RunRequest(PreviewRequest):
    connect_timeout_ms: int = Field(default=5000,ge=100,le=60000); read_timeout_ms: int = Field(default=30000,ge=100,le=120000); total_timeout_ms: int = Field(default=60000,ge=100,le=300000); max_response_bytes: int = Field(default=2*1024*1024,ge=1024,le=20*1024*1024)

class ScenarioStepIn(BaseModel):
    seq: int = Field(ge=1); name: str = Field(min_length=1,max_length=255); interface_id: str | None = None; request_override: dict = Field(default_factory=dict); preconditions: list[dict] = Field(default_factory=list); extracts: list[dict] = Field(default_factory=list); assertions: list[dict] = Field(default_factory=list); expected_result: str = ""; timeout_ms: int = Field(default=30000,ge=100,le=300000); retry_count: int = Field(default=0,ge=0,le=3); continue_on_failure: bool = False

class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1,max_length=255); description: str = ""; scenario_type: Literal["api"] = "api"; priority: Literal["P0","P1","P2","P3"] = "P2"; requirement_module_ids: list[str] = Field(default_factory=list); steps: list[ScenarioStepIn] = Field(min_length=1)

class ScenarioUpdate(ScenarioCreate): revision: int = Field(ge=1)
class ExecutionCreate(BaseModel): scenario_id: str; environment_id: str
class ScenarioCandidateRequest(BaseModel): requirement_module_ids: list[str] = Field(default_factory=list); interface_ids: list[str] = Field(min_length=1,max_length=5)
