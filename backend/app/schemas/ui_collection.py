from pydantic import BaseModel, Field


class UiCollectionCreate(BaseModel):
    environment_id: str
    start_url: str = Field(min_length=1, max_length=2048)
    allowed_paths: list[str] = Field(min_length=1, max_length=50)
    max_pages: int = Field(default=1, ge=1, le=10)
    max_elements_per_page: int = Field(default=200, ge=1, le=500)
    max_iframes: int = Field(default=10, ge=0, le=30)
    total_timeout_ms: int = Field(default=60000, ge=1000, le=300000)


class CollectedAttributes(BaseModel):
    test_id: str | None = Field(default=None, max_length=255)
    id: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    label: str | None = Field(default=None, max_length=512)
    placeholder: str | None = Field(default=None, max_length=512)
    text: str = Field(default="", max_length=512)


class CollectedElementPayload(BaseModel):
    element_key: str = Field(min_length=1, max_length=160)
    tag: str = Field(min_length=1, max_length=32)
    role: str | None = Field(default=None, max_length=64)
    accessible_name: str = Field(default="", max_length=512)
    attributes: CollectedAttributes
    visible: bool
    enabled: bool
    actionable: bool
    checked: bool | None = None
    frame_path: list[dict] = Field(default_factory=list, max_length=10)


class UiLocatorRevisionCreate(BaseModel):
    candidate_id: str
    ui_element_id: str


class UiLocatorRevisionDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
