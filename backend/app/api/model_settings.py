from fastapi import APIRouter, Request
import httpx

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.schemas.model_settings import DefaultConfigRequest, ModelConfigCreate, ModelConfigProbeRequest, ModelConfigUpdate
from app.services import llm_probe, model_configs

router = APIRouter(prefix="/settings/model-configs", tags=["model-settings"])


@router.get("")
async def list_model_configs(request: Request, db: DbSession, user: CurrentUser):
    return success(await model_configs.list_all(db, user), request.state.trace_id)


@router.post("", status_code=201)
async def create_model_config(data: ModelConfigCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(model_configs.view(await model_configs.create(db, user, data)), request.state.trace_id)


@router.post("/test-connection")
async def test_temporary_connection(data: ModelConfigProbeRequest, request: Request, db: DbSession, user: CurrentUser):
    model_configs.require_admin(user)
    llm_probe.validate_protocol(data.protocol)
    return success(await llm_probe.probe_config(data, data.api_key.get_secret_value() if data.api_key else ""), request.state.trace_id)

@router.post("/test-structured-output")
async def test_temporary_structured_output(data: ModelConfigProbeRequest, request: Request, db: DbSession, user: CurrentUser):
    model_configs.require_admin(user)
    llm_probe.validate_protocol(data.protocol)
    return success(await llm_probe.test_structured_output(data, data.api_key.get_secret_value() if data.api_key else ""), request.state.trace_id)

@router.get("/{config_id}/models")
async def list_remote_models(config_id: str, request: Request, db: DbSession, user: CurrentUser):
    row, api_key = await model_configs.saved_probe_secret(db, user, config_id)
    base = str(row.base_url or llm_probe.DEFAULT_BASE_URLS[row.protocol]).rstrip("/")
    headers = {}
    params = {}
    if row.protocol == llm_probe.OPENAI_CHAT:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        url = f"{base}/models"
    elif row.protocol == llm_probe.ANTHROPIC:
        headers = {"anthropic-version": str((row.extra_params or {}).get("api_version") or "2023-06-01")}
        if api_key: headers["x-api-key"] = api_key
        url = f"{base}/models"
    elif row.protocol == llm_probe.GEMINI:
        if api_key: params["key"] = api_key
        url = f"{base}/models"
    else:
        return success({"items": [], "message": "当前协议不支持模型列表接口"}, request.state.trace_id)
    async with httpx.AsyncClient(timeout=httpx.Timeout(float(row.timeout_seconds))) as client:
        response = await client.get(url, headers=headers, params=params)
        # DeepSeek's Anthropic-compatible endpoint serves messages but not /models.
        if response.status_code == 404 and row.provider.lower() == "deepseek" and row.protocol == llm_probe.ANTHROPIC:
            fallback_base = base.removesuffix("/anthropic").rstrip("/") + "/v1"
            response = await client.get(f"{fallback_base}/models", headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
    if response.status_code >= 400:
        detail = f"HTTP {response.status_code}"
        try:
            body = response.json()
            error = body.get("error") or body.get("message")
            if isinstance(error, dict): error = error.get("message") or error.get("status")
            if error: detail += f": {str(error)[:300]}"
        except ValueError:
            pass
        return success({"items": [], "message": detail}, request.state.trace_id)
    try:
        body = response.json()
        if row.protocol == llm_probe.GEMINI:
            items = [str(item.get("name", "")).removeprefix("models/") for item in body.get("models", []) if item.get("name")]
        else:
            items = [item.get("id") for item in body.get("data", []) if item.get("id")]
    except (ValueError, TypeError):
        return success({"items": [], "message": "模型列表响应不是有效 JSON"}, request.state.trace_id)
    return success({"items": items}, request.state.trace_id)


@router.patch("/{config_id}")
async def update_model_config(config_id: str, data: ModelConfigUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(model_configs.view(await model_configs.update_config(db, user, config_id, data)), request.state.trace_id)


@router.post("/{config_id}/set-default")
async def set_default_model_config(config_id: str, data: DefaultConfigRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(model_configs.view(await model_configs.set_default(db, user, config_id, data.revision)), request.state.trace_id)


@router.post("/{config_id}/test-connection")
async def test_saved_connection(config_id: str, request: Request, db: DbSession, user: CurrentUser):
    row, api_key = await model_configs.saved_probe_secret(db, user, config_id)
    return success(await llm_probe.probe_config(row, api_key), request.state.trace_id)

@router.post("/{config_id}/test-structured-output")
async def test_saved_structured_output(config_id: str, request: Request, db: DbSession, user: CurrentUser):
    row, api_key = await model_configs.saved_probe_secret(db, user, config_id)
    return success(await llm_probe.test_structured_output(row, api_key), request.state.trace_id)
