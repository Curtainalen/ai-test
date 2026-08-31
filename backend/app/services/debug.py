from copy import deepcopy
from sqlalchemy import select
from app.errors import AppError
from app.models import ApiInterface,DebugRun,TestEnvironment
from app.services.http_execution import execute_request,request_snapshot
from app.services.identity import require_membership
from app.services.request_engine import compose_request

def base_request(interface):
    imported=interface.imported_snapshot or {}; manual=interface.manual_config or {}
    return {"method":interface.method,"url":interface.path,"headers":manual.get("headers",{}),"params":manual.get("params",{}),"cookies":manual.get("cookies",{}),"body_type":manual.get("body_type","none"),"body":manual.get("body"),"auth":manual.get("auth",{}),"variables":manual.get("variables",{}),"extracts":manual.get("extracts",[]),"assertions":manual.get("assertions",[])}

async def compose(db,project_id,user,data):
    await require_membership(db,project_id,user); env=await db.scalar(select(TestEnvironment).where(TestEnvironment.id==data.environment_id,TestEnvironment.project_id==project_id,TestEnvironment.is_enabled.is_(True)))
    if not env: raise AppError("RESOURCE_NOT_FOUND","环境不存在或未启用",404)
    interface=None
    if data.interface_id:
        interface=await db.scalar(select(ApiInterface).where(ApiInterface.id==data.interface_id,ApiInterface.project_id==project_id,ApiInterface.is_deleted.is_(False)))
        if not interface: raise AppError("RESOURCE_NOT_FOUND","接口不存在",404)
    request=data.request.model_dump() if data.request else base_request(interface)
    request={**request,**deepcopy(data.request_override)}
    environment={"base_url":env.base_url,"variables":{**(env.variables or {}),**(env.secret_refs or {})},"global_headers":env.global_headers or {}}
    return compose_request(request,environment,[data.case_variables,data.step_variables]),env,interface

async def run(db,project_id,user,data):
    composed,env,interface=await compose(db,project_id,user,data); result=await execute_request(composed["request"],connect_timeout_ms=data.connect_timeout_ms,read_timeout_ms=data.read_timeout_ms,total_timeout_ms=data.total_timeout_ms,max_response_bytes=data.max_response_bytes,known_secrets=composed["sensitive_values"])
    row=DebugRun(project_id=project_id,interface_id=interface.id if interface else None,environment_id=env.id,request_snapshot=composed["preview"],response_snapshot=result["response"],status=result["status"],duration_ms=result["duration_ms"],created_by=user.id); db.add(row); await db.commit(); await db.refresh(row)
    return {"history_id":row.id,"request_preview":composed["preview"],**result}
