from datetime import datetime
from fastapi import APIRouter,Header,Request
from app.dependencies import CurrentUser,DbSession
from app.response import success
from app.schemas.assets import ExecutionCreate,PreviewRequest,RunRequest,ScenarioCreate,ScenarioUpdate
from app.services import debug,executions,scenarios

router=APIRouter(prefix="/projects/{project_id}",tags=["testing"])
@router.post("/requests/preview")
async def preview(project_id:str,data:PreviewRequest,request:Request,db:DbSession,user:CurrentUser):
    composed,_,_=await debug.compose(db,project_id,user,data); return success({"request_preview":composed["preview"],"valid":True},request.state.trace_id)
@router.post("/requests/run")
async def run(project_id:str,data:RunRequest,request:Request,db:DbSession,user:CurrentUser): return success(await debug.run(db,project_id,user,data),request.state.trace_id)
@router.get("/scenarios")
async def list_scenarios(project_id:str,request:Request,db:DbSession,user:CurrentUser): return success(await scenarios.list_all(db,project_id,user),request.state.trace_id)
@router.post("/scenarios",status_code=201)
async def create_scenario(project_id:str,data:ScenarioCreate,request:Request,db:DbSession,user:CurrentUser): return success(await scenarios.create(db,project_id,user,data),request.state.trace_id)
@router.patch("/scenarios/{scenario_id}")
async def update_scenario(project_id:str,scenario_id:str,data:ScenarioUpdate,request:Request,db:DbSession,user:CurrentUser): return success(await scenarios.update(db,project_id,user,scenario_id,data),request.state.trace_id)
@router.post("/scenarios/{scenario_id}/confirm")
async def confirm_scenario(project_id:str,scenario_id:str,revision:int,request:Request,db:DbSession,user:CurrentUser): return success(await scenarios.confirm(db,project_id,user,scenario_id,revision),request.state.trace_id)
@router.post("/executions",status_code=202)
async def create_execution(project_id:str,data:ExecutionCreate,request:Request,db:DbSession,user:CurrentUser,idempotency_key:str=Header(alias="Idempotency-Key")):
    row,created=await executions.create(db,project_id,user,data.scenario_id,data.environment_id,idempotency_key); return success({**executions.task_view(row),"created":created},request.state.trace_id)
@router.get("/executions/{execution_id}")
async def execution_detail(project_id:str,execution_id:str,request:Request,db:DbSession,user:CurrentUser): return success(await executions.detail(db,project_id,user,execution_id),request.state.trace_id)
@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(project_id:str,execution_id:str,request:Request,db:DbSession,user:CurrentUser): return success(executions.task_view(await executions.cancel(db,project_id,user,execution_id)),request.state.trace_id)
@router.get("/reports")
async def reports(project_id:str,request:Request,db:DbSession,user:CurrentUser,status:str|None=None,environment_id:str|None=None,scenario_id:str|None=None,created_by:str|None=None,started_from:datetime|None=None,started_to:datetime|None=None): return success([executions.report_view(r) for r in await executions.list_reports(db,project_id,user,status,environment_id,scenario_id,created_by,started_from,started_to)],request.state.trace_id)
@router.get("/reports/{report_id}")
async def report_detail(project_id:str,report_id:str,request:Request,db:DbSession,user:CurrentUser): return success(await executions.report_detail(db,project_id,user,report_id),request.state.trace_id)

@router.get("/requirement-coverage")
async def coverage(project_id:str,request:Request,db:DbSession,user:CurrentUser): return success(await executions.requirement_coverage(db,project_id,user),request.state.trace_id)
