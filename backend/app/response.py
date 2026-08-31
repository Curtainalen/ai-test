from typing import Any


def success(data: Any = None, trace_id: str | None = None) -> dict:
    return {"success": True, "data": data, "trace_id": trace_id}


def failure(code: str, message: str, details: Any = None, trace_id: str | None = None) -> dict:
    return {"success": False, "error": {"code": code, "message": message, "details": details}, "trace_id": trace_id}
