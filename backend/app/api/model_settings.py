from fastapi import APIRouter, Request

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
