from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LlmResult:
    data: dict[str, Any]
    call_id: str
    model_config_revision_id: str
    input_tokens: int | None
    output_tokens: int | None
    usage_unknown: bool
