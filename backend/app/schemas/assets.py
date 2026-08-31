from typing import Any, Literal
from pydantic import BaseModel, Field

class RequirementModuleUpdate(BaseModel):
    name: str = Field(min_length=1,max_length=255); description: str = Field(default="",max_length=10000); source_block_ids: list[str]; revision: int = Field(ge=1)

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
