"""需求文档敏感信息识别与脱敏。

该模块只做确定性的本地处理，不调用模型。真实值只存在于解析任务的短生命周期内，
对外暴露的正文统一替换为 data:// 或 secret:// 引用。
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SensitiveMatch:
    """敏感片段的非敏感描述，禁止保存匹配到的真实值。"""

    start: int
    end: int
    field: str
    kind: str
    reference: str
    confidence: float


# 字段名比字段值更可靠；值模式只在字段上下文存在时启用，降低误报。
FIELD_ALIASES = {
    "password": ("login_password", "secret"),
    "passwd": ("login_password", "secret"),
    "pwd": ("login_password", "secret"),
    "密码": ("login_password", "secret"),
    "token": ("access_token", "secret"),
    "access_token": ("access_token", "secret"),
    "令牌": ("access_token", "secret"),
    "cookie": ("session_cookie", "secret"),
    "authorization": ("authorization", "secret"),
    "api_key": ("api_key", "secret"),
    "apikey": ("api_key", "secret"),
    "secret": ("secret_value", "secret"),
    "username": ("login_username", "data"),
    "user_name": ("login_username", "data"),
    "用户名": ("login_username", "data"),
    "账号": ("login_username", "data"),
    "email": ("contact_email", "data"),
    "邮箱": ("contact_email", "data"),
    "phone": ("contact_phone", "data"),
    "mobile": ("contact_phone", "data"),
    "手机号": ("contact_phone", "data"),
}

_FIELD_PATTERN = re.compile(
    r"(?P<label>password|passwd|pwd|token|access[_ -]?token|令牌|cookie|authorization|api[_ -]?key|apikey|secret|username|user[_ -]?name|密码|用户名|账号|email|邮箱|phone|mobile|手机号)"
    r"\s*(?:是|为|=|:|：)\s*(?P<value>[^\s,，;；。\n]+)",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"\bBearer\s+(?P<value>[A-Za-z0-9._~+/=-]{12,})\b", re.IGNORECASE)
_JSON_FIELD_PATTERN = re.compile(
    r"[\"']?(?P<label>password|passwd|pwd|token|access[_ -]?token|令牌|cookie|authorization|api[_ -]?key|apikey|secret|username|user[_ -]?name|密码|用户名|账号|email|邮箱|phone|mobile|手机号)[\"']?"
    r"\s*:\s*[\"'](?P<value>[^\"']+)[\"']",
    re.IGNORECASE,
)


def _normalize_label(label: str) -> tuple[str, str]:
    key = re.sub(r"[ _-]+", "_", label.strip().lower())
    return FIELD_ALIASES.get(key, ("document_secret", "secret"))


def sanitize_text(text: str) -> tuple[str, list[dict], list[dict]]:
    """将正文中的字段值替换成引用，并返回敏感片段元数据和数据项候选。"""
    if not text:
        return text, [], []
    matches: list[SensitiveMatch] = []
    items: dict[str, dict] = {}
    # JSON 字段优先使用专用规则，避免通用规则把结尾引号或大括号算进敏感值。
    json_ranges = [(match.start(), match.end()) for match in _JSON_FIELD_PATTERN.finditer(text)]
    for match in _FIELD_PATTERN.finditer(text):
        if any(start <= match.start("label") < end for start, end in json_ranges):
            continue
        label = match.group("label")
        value = match.group("value")
        # 规则说明不是凭据，例如“密码至少 8 位”不应被替换。
        if label.lower() in {"password", "密码", "pwd"} and re.fullmatch(r"\d+", value):
            continue
        name, kind = _normalize_label(label)
        reference = f"secret://{name}" if kind == "secret" else f"data://{name}"
        matches.append(SensitiveMatch(match.start("value"), match.end("value"), name, kind, reference, 0.96))
        items.setdefault(name, {"name": name, "label": name, "data_type": "string", "value_ref": reference,
                                "reference": reference, "preview": "***" if kind == "secret" else "待配置",
                                "sensitive": kind == "secret", "sensitivity": kind,
                                "source_block_seq": None, "source_block_ids": [], "constraints": {},
                                "status": "pending_confirmation"})
    # Prompt 和结构化内容经常使用 JSON；补充识别 "password": "..." 形式。
    for match in _JSON_FIELD_PATTERN.finditer(text):
        if any(item.start == match.start("value") for item in matches):
            continue
        label = match.group("label")
        value = match.group("value")
        if label.lower() in {"password", "密码", "pwd"} and re.fullmatch(r"\d+", value):
            continue
        name, kind = _normalize_label(label)
        reference = f"secret://{name}" if kind == "secret" else f"data://{name}"
        matches.append(SensitiveMatch(match.start("value"), match.end("value"), name, kind, reference, 0.96))
        items.setdefault(name, {"name": name, "label": name, "data_type": "string", "value_ref": reference,
                                "reference": reference, "preview": "***" if kind == "secret" else "待配置",
                                "sensitive": kind == "secret", "sensitivity": kind, "source_block_seq": None,
                                "source_block_ids": [], "constraints": {}, "status": "pending_confirmation"})
    for match in _BEARER_PATTERN.finditer(text):
        name, kind = "authorization", "secret"
        reference = "secret://authorization"
        matches.append(SensitiveMatch(match.start("value"), match.end("value"), name, kind, reference, 0.99))
        items.setdefault(name, {"name": name, "label": name, "data_type": "string", "value_ref": reference,
                                "reference": reference, "preview": "***", "sensitive": True,
                                "sensitivity": "secret", "source_block_seq": None, "source_block_ids": [],
                                "constraints": {}, "status": "pending_confirmation"})
    # 从后向前替换，保证原始下标不会因替换而失效。
    sanitized = text
    for item in sorted(matches, key=lambda current: current.start, reverse=True):
        sanitized = sanitized[:item.start] + f"[{item.reference}]" + sanitized[item.end:]
    spans = [{"start": item.start, "end": item.end, "field": item.field, "kind": item.kind,
              "reference": item.reference, "confidence": item.confidence} for item in matches]
    return sanitized, spans, list(items.values())


def sanitize_block(block: dict) -> tuple[dict, list[dict]]:
    """生成 ContentBlock 的脱敏视图，同时保留原始字段供密文存储。"""
    original = str(block.get("content") or "")
    sanitized, spans, items = sanitize_text(original)
    for item in items:
        item["source_block_seq"] = block.get("seq")
    result = dict(block)
    result["content"] = sanitized
    # 表格等结构化字段也可能包含凭据，因此不能只脱敏展示用的 Markdown 文本。
    def sanitize_value(value):
        if isinstance(value, str):
            return sanitize_text(value)[0]
        if isinstance(value, list):
            return [sanitize_value(item) for item in value]
        if isinstance(value, dict):
            return {key: sanitize_value(item) for key, item in value.items()}
        return value
    result["structured_content"] = sanitize_value(block.get("structured_content") or {})
    structured = result["structured_content"]
    # 表格单元格通常只有值，必须结合表头识别敏感列，例如“API Key”列下的真实密钥。
    if isinstance(structured, dict) and isinstance(structured.get("headers"), list) and isinstance(structured.get("rows"), list):
        sensitive_columns: dict[int, tuple[str, str]] = {}
        for index, header in enumerate(structured["headers"]):
            normalized_header = re.sub(r"[ _-]+", "_", str(header).strip().lower())
            if normalized_header in FIELD_ALIASES:
                sensitive_columns[index] = FIELD_ALIASES[normalized_header]
        for row in structured["rows"]:
            if not isinstance(row, list):
                continue
            for index, (name, kind) in sensitive_columns.items():
                if index >= len(row) or not str(row[index]).strip():
                    continue
                reference = f"secret://{name}" if kind == "secret" else f"data://{name}"
                row[index] = f"[{reference}]"
                items.append({"name": name, "label": name, "data_type": "string", "value_ref": reference,
                              "reference": reference, "preview": "***" if kind == "secret" else "待配置",
                              "sensitive": kind == "secret", "sensitivity": kind,
                              "source_block_seq": block.get("seq"), "source_block_ids": [], "constraints": {},
                              "status": "pending_confirmation"})
    result["sensitive_spans"] = spans
    result["parse_warnings"] = list(block.get("parse_warnings") or [])
    if block.get("needs_correction"):
        result["parse_warnings"].append("内容置信度不足，需要人工校正")
    # 同一字段可能同时出现在正文和表格中，数据目录按引用去重，但来源块仍由 Worker 汇总。
    unique_items = list({item["reference"]: item for item in items}.values())
    return result, unique_items


def contains_suspected_secret(text: str) -> bool:
    """校正与 Prompt 的最后一道拦截，防止真实凭据或个人数据重新流入正文。"""
    # JSON 字段先单独判断，避免通用的“字段:值”规则把结尾引号当成引用的一部分。
    json_ranges = [(match.start(), match.end()) for match in _JSON_FIELD_PATTERN.finditer(text or "")]
    for match in _FIELD_PATTERN.finditer(text or ""):
        if any(start <= match.start("label") < end for start, end in json_ranges):
            continue
        label = match.group("label").lower()
        value = match.group("value").strip("[]'\" ")
        # “密码至少 8 位”属于规则说明，不是凭据；校正拦截必须与解析脱敏规则保持一致。
        if label in {"password", "密码", "pwd"} and re.fullmatch(r"\d+", value):
            continue
        # 已统一替换的掩码也是安全值；允许网关重复处理已经脱敏的上下文。
        if value not in {"******", "***"} and not value.startswith(("secret://", "data://")):
            return True
    for match in _JSON_FIELD_PATTERN.finditer(text or ""):
        label = match.group("label").lower()
        value = match.group("value")
        if label in {"password", "密码", "pwd"} and re.fullmatch(r"\d+", value):
            continue
        if value not in {"******", "***"} and not value.startswith(("secret://", "data://")):
            return True
    return bool(_BEARER_PATTERN.search(text or ""))


def serialized_raw_block(block: dict) -> str:
    """将解析器原始输出序列化后交给加密层，避免原文进入 JSON 日志或普通字段。"""
    return json.dumps({"content": block.get("content", ""), "structured_content": block.get("structured_content", {})}, ensure_ascii=False)
