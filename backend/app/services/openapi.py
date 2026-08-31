from __future__ import annotations
import hashlib, json, re
from copy import deepcopy
import yaml
from app.errors import AppError

METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def parse_spec(content: bytes) -> dict:
    if len(content) > 5 * 1024 * 1024: raise AppError("OPENAPI_TOO_LARGE", "OpenAPI 文件超过限制", 413)
    try: data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        try: data = yaml.safe_load(content)
        except yaml.YAMLError as exc: raise AppError("OPENAPI_INVALID", "OpenAPI JSON/YAML 无法解析", 422) from exc
    if not isinstance(data, dict): raise AppError("OPENAPI_INVALID", "OpenAPI 根节点必须是对象", 422)
    if data.get("swagger") == "2.0": version = "2.0"
    elif str(data.get("openapi", "")).startswith(("3.0", "3.1")): version = str(data["openapi"])
    else: raise AppError("OPENAPI_UNSUPPORTED", "仅支持 Swagger 2.0、OpenAPI 3.0/3.1", 422)
    return {"version": version, "raw": data, "interfaces": normalize_spec(data, version), "warnings": collect_warnings(data)}


def collect_warnings(data: dict) -> list[dict]:
    warnings=[]
    for path,path_item in (data.get("paths") or {}).items():
        for method,operation in (path_item or {}).items():
            if method.lower() in METHODS and isinstance(operation,dict):
                for field in ("callbacks","webhooks"):
                    if operation.get(field): warnings.append({"code":"OPENAPI_PARTIAL_SUPPORT","path":path,"method":method.upper(),"field":field})
    if data.get("webhooks"): warnings.append({"code":"OPENAPI_PARTIAL_SUPPORT","field":"webhooks"})
    return warnings


def normalize_path(path: str) -> str:
    path = re.sub(r"/+", "/", "/" + path.strip("/"))
    return re.sub(r"\{[^{}]+\}", "{}", path)


def normalize_spec(data: dict, version: str) -> list[dict]:
    interfaces = []
    for path, path_item in (data.get("paths") or {}).items():
        if not isinstance(path_item, dict): continue
        common = path_item.get("parameters") or []
        for method, operation in path_item.items():
            if method.lower() not in METHODS or not isinstance(operation, dict): continue
            tags = operation.get("tags") or []
            module = tags[0] if tags else next((segment for segment in str(path).split("/") if segment and not segment.startswith("{")), "默认模块")
            request_body = operation.get("requestBody") or {}
            if version == "2.0":
                body_param = next((item for item in operation.get("parameters", []) if item.get("in") == "body"), None)
                request_body = {"content": {"application/json": {"schema": (body_param or {}).get("schema", {})}}} if body_param else {}
            stable_key = hashlib.sha256(f"{method.upper()} {normalize_path(path)}".encode()).hexdigest()
            interfaces.append({"stable_key": stable_key, "method": method.upper(), "path": path, "normalized_path": normalize_path(path), "summary": operation.get("summary") or operation.get("operationId") or "", "tags": tags, "module": module, "parameters": [*common, *(operation.get("parameters") or [])], "request_body": request_body, "responses": operation.get("responses") or {}, "security": operation.get("security", data.get("security", []))})
    return sorted(interfaces, key=lambda item: (item["path"], item["method"]))


def diff_interfaces(existing: list[dict], incoming: list[dict]) -> dict:
    old, new = {item["stable_key"]: item for item in existing}, {item["stable_key"]: item for item in incoming}
    added = [deepcopy(new[key]) for key in new.keys() - old.keys()]
    deleted = [deepcopy(old[key]) for key in old.keys() - new.keys()]
    modified, unchanged = [], []
    for key in new.keys() & old.keys():
        left, right = {k:v for k,v in old[key].items() if k not in {"revision", "manual_config"}}, {k:v for k,v in new[key].items() if k not in {"revision", "manual_config"}}
        (modified if left != right else unchanged).append({"before": deepcopy(old[key]), "after": deepcopy(new[key])} if left != right else deepcopy(new[key]))
    return {"added": added, "modified": modified, "deleted": deleted, "unchanged": unchanged}
