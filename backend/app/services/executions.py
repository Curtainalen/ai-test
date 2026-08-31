from __future__ import annotations
from copy import deepcopy
from datetime import UTC,datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.errors import AppError
from app.models import ApiInterface,ExecutionStep,ExecutionTask,Project,ReportStep,RequirementModule,ScenarioStep,TestEnvironment,TestReport,TestScenario,User
from app.services.identity import require_membership
from app.services.queue import enqueue_unique

def task_view(row,steps=None): return {"id":row.id,"project_id":row.project_id,"scenario_id":row.scenario_id,"environment_id":row.environment_id,"status":row.status,"cancel_requested":row.cancel_requested,"event_version":row.event_version,"error_category":row.error_category,"error_message":row.error_message,"started_at":row.started_at.isoformat() if row.started_at else None,"finished_at":row.finished_at.isoformat() if row.finished_at else None,"steps":[step_view(s) for s in (steps or [])]}
def step_view(s): return {"id":s.id,"seq":s.seq,"name":s.name,"status":s.status,"started_at":s.started_at.isoformat() if s.started_at else None,"finished_at":s.finished_at.isoformat() if s.finished_at else None,"duration_ms":s.duration_ms,"request":s.request_snapshot,"response":s.response_snapshot,"extracted":s.extracted,"assertions":s.assertions,"error_category":s.error_category,"error_message":s.error_message}
def report_view(r,steps=None): return {"id":r.id,"execution_id":r.execution_id,"status":r.status,"summary":r.summary,"project":r.project_snapshot,"environment":r.environment_snapshot,"scenario":r.scenario_snapshot,"requirements":r.requirement_snapshot,"triggered_by":r.triggered_by_snapshot,"started_at":r.started_at.isoformat() if r.started_at else None,"finished_at":r.finished_at.isoformat() if r.finished_at else None,"created_at":r.created_at.isoformat() if r.created_at else None,"steps":[{"seq":s.seq,"name":s.name,"status":s.status,"duration_ms":s.duration_ms,"request":s.request_snapshot,"response":s.response_snapshot,"extracted":s.extracted,"assertions":s.assertions,"error_category":s.error_category,"error_message":s.error_message,"repro_steps":s.repro_steps} for s in (steps or [])]}


def coverage_status(module_status:str,linked_scenarios:list,latest_report)->str:
    if module_status in {"changed","needs_review"}: return "needs_review"
    if not linked_scenarios: return "unplanned"
    if latest_report is not None: return "passed" if latest_report.status=="passed" else "failed"
    if any(s.status=="confirmed" for s in linked_scenarios): return "covered"
    return "pending_confirmation"

async def create(db:AsyncSession,project_id:str,user:User,scenario_id:str,environment_id:str,idempotency_key:str):
    await require_membership(db,project_id,user)
    if not idempotency_key or len(idempotency_key)>128: raise AppError("IDEMPOTENCY_KEY_REQUIRED","必须提供有效 Idempotency-Key",422)
    existing=await db.scalar(select(ExecutionTask).where(ExecutionTask.project_id==project_id,ExecutionTask.idempotency_key==idempotency_key))
    if existing: return existing,False
    scenario=await db.scalar(select(TestScenario).where(TestScenario.id==scenario_id,TestScenario.project_id==project_id)); env=await db.scalar(select(TestEnvironment).where(TestEnvironment.id==environment_id,TestEnvironment.project_id==project_id,TestEnvironment.is_enabled.is_(True)))
    if not scenario or not env: raise AppError("RESOURCE_NOT_FOUND","场景或环境不存在",404)
    if scenario.status!="confirmed": raise AppError("SCENARIO_NOT_CONFIRMED","未确认场景不能执行",409)
    steps=(await db.scalars(select(ScenarioStep).where(ScenarioStep.scenario_id==scenario.id).order_by(ScenarioStep.seq))).all()
    snapshot={"id":scenario.id,"name":scenario.name,"description":scenario.description,"version":scenario.version,"revision":scenario.revision,"requirement_module_ids":scenario.requirement_module_ids,"steps":[{"seq":s.seq,"name":s.name,"interface_id":s.interface_id,"request_override":s.request_override,"extracts":s.extracts,"assertions":s.assertions,"expected_result":s.expected_result,"timeout_ms":s.timeout_ms,"retry_count":s.retry_count,"continue_on_failure":s.continue_on_failure} for s in steps]}
    env_snapshot={"id":env.id,"name":env.name,"base_url":env.base_url,"variables":env.variables,"global_headers":env.global_headers,"secret_refs":env.secret_refs,"revision":env.revision}
    row=ExecutionTask(project_id=project_id,scenario_id=scenario.id,environment_id=env.id,idempotency_key=idempotency_key,scenario_snapshot=snapshot,environment_snapshot=env_snapshot,created_by=user.id)
    db.add(row)
    try: await db.commit()
    except IntegrityError:
        await db.rollback(); row=await db.scalar(select(ExecutionTask).where(ExecutionTask.project_id==project_id,ExecutionTask.idempotency_key==idempotency_key)); return row,False
    try:
        enqueue_unique("app.worker_jobs.execute_scenario_job",row.id,900)
    except AppError:
        row.status="failed"; row.error_category="executor_error"; row.error_message="任务队列不可用"; row.finished_at=datetime.now(UTC); await db.commit(); raise
    return row,True

async def detail(db,project_id,user,execution_id):
    await require_membership(db,project_id,user); row=await db.scalar(select(ExecutionTask).where(ExecutionTask.id==execution_id,ExecutionTask.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","执行任务不存在",404)
    steps=(await db.scalars(select(ExecutionStep).where(ExecutionStep.execution_id==row.id).order_by(ExecutionStep.seq))).all(); return task_view(row,steps)

async def cancel(db,project_id,user,execution_id):
    await require_membership(db,project_id,user); row=await db.scalar(select(ExecutionTask).where(ExecutionTask.id==execution_id,ExecutionTask.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","执行任务不存在",404)
    if row.status not in {"pending","running"}: raise AppError("EXECUTION_NOT_CANCELABLE","任务已进入终态",409)
    row.cancel_requested=True; row.event_version+=1; await db.commit(); return row

async def list_reports(db,project_id,user,status=None,environment_id=None,scenario_id=None,created_by=None,started_from=None,started_to=None):
    await require_membership(db,project_id,user); query=select(TestReport).where(TestReport.project_id==project_id)
    if status: query=query.where(TestReport.status==status)
    if environment_id: query=query.where(TestReport.environment_snapshot["id"].as_string()==environment_id)
    if scenario_id: query=query.where(TestReport.scenario_snapshot["id"].as_string()==scenario_id)
    if created_by: query=query.where(TestReport.triggered_by_snapshot["id"].as_string()==created_by)
    if started_from: query=query.where(TestReport.started_at>=started_from)
    if started_to: query=query.where(TestReport.started_at<=started_to)
    return list((await db.scalars(query.order_by(TestReport.created_at.desc()))).all())


async def requirement_coverage(db,project_id,user):
    await require_membership(db,project_id,user)
    modules=(await db.scalars(select(RequirementModule).where(RequirementModule.project_id==project_id))).all()
    scenarios=(await db.scalars(select(TestScenario).where(TestScenario.project_id==project_id))).all()
    reports=(await db.scalars(select(TestReport).where(TestReport.project_id==project_id).order_by(TestReport.created_at.desc()))).all()
    items=[]
    for module in modules:
        linked=[s for s in scenarios if module.id in (s.requirement_module_ids or [])]
        linked_ids={s.id for s in linked}
        latest=next((r for r in reports if (r.scenario_snapshot or {}).get("id") in linked_ids),None)
        status=coverage_status(module.status,linked,latest)
        items.append({"requirement_module_id":module.id,"name":module.name,"status":status,"scenario_ids":[s.id for s in linked]})
    return items

async def report_detail(db,project_id,user,report_id):
    await require_membership(db,project_id,user); row=await db.scalar(select(TestReport).where(TestReport.id==report_id,TestReport.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","报告不存在",404)
    steps=(await db.scalars(select(ReportStep).where(ReportStep.report_id==row.id).order_by(ReportStep.seq))).all(); return report_view(row,steps)
