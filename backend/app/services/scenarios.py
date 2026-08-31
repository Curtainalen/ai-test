from __future__ import annotations
from datetime import UTC,datetime
from sqlalchemy import delete,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.errors import AppError
from app.models import ApiInterface,RequirementCoverage,RequirementModule,ScenarioStep,TestScenario,User
from app.services.identity import require_membership

def scenario_view(row,steps): return {"id":row.id,"project_id":row.project_id,"name":row.name,"description":row.description,"scenario_type":row.scenario_type,"priority":row.priority,"version":row.version,"revision":row.revision,"status":row.status,"requirement_module_ids":row.requirement_module_ids,"steps":[{"id":s.id,"seq":s.seq,"name":s.name,"interface_id":s.interface_id,"request_override":s.request_override,"preconditions":s.preconditions,"extracts":s.extracts,"assertions":s.assertions,"expected_result":s.expected_result,"timeout_ms":s.timeout_ms,"retry_count":s.retry_count,"continue_on_failure":s.continue_on_failure} for s in steps]}

async def _validate_refs(db,project_id,module_ids,steps):
    if module_ids:
        modules=(await db.scalars(select(RequirementModule).where(RequirementModule.project_id==project_id,RequirementModule.id.in_(module_ids)))).all()
        if len(modules)!=len(set(module_ids)) or any(m.status!="confirmed" for m in modules): raise AppError("REQUIREMENT_MODULE_INVALID","场景只能关联本项目已确认需求模块",422)
    interface_ids={step.interface_id for step in steps if step.interface_id}
    if interface_ids:
        count=len((await db.scalars(select(ApiInterface.id).where(ApiInterface.project_id==project_id,ApiInterface.id.in_(interface_ids),ApiInterface.is_deleted.is_(False)))).all())
        if count!=len(interface_ids): raise AppError("INTERFACE_INVALID","场景步骤接口不属于当前项目",422)
    if len({step.seq for step in steps})!=len(steps): raise AppError("SCENARIO_STEP_SEQUENCE_DUPLICATE","步骤序号不能重复",422)

async def create(db:AsyncSession,project_id:str,user:User,data):
    await require_membership(db,project_id,user); await _validate_refs(db,project_id,data.requirement_module_ids,data.steps)
    row=TestScenario(project_id=project_id,name=data.name,description=data.description,scenario_type=data.scenario_type,priority=data.priority,requirement_module_ids=data.requirement_module_ids,created_by=user.id,status="draft")
    db.add(row); await db.flush()
    for step in data.steps: db.add(ScenarioStep(project_id=project_id,scenario_id=row.id,**step.model_dump()))
    await db.commit(); return await get(db,project_id,user,row.id)

async def get(db,project_id,user,scenario_id):
    await require_membership(db,project_id,user); row=await db.scalar(select(TestScenario).where(TestScenario.id==scenario_id,TestScenario.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","场景不存在",404)
    steps=(await db.scalars(select(ScenarioStep).where(ScenarioStep.scenario_id==row.id).order_by(ScenarioStep.seq))).all(); return scenario_view(row,steps)

async def list_all(db,project_id,user):
    await require_membership(db,project_id,user); rows=(await db.scalars(select(TestScenario).where(TestScenario.project_id==project_id).order_by(TestScenario.updated_at.desc()))).all(); return [await get(db,project_id,user,row.id) for row in rows]

async def update(db,project_id,user,scenario_id,data):
    await require_membership(db,project_id,user); row=await db.scalar(select(TestScenario).where(TestScenario.id==scenario_id,TestScenario.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","场景不存在",404)
    if row.revision!=data.revision: raise AppError("REVISION_CONFLICT","场景已被其他用户修改",409,{"current_revision":row.revision})
    await _validate_refs(db,project_id,data.requirement_module_ids,data.steps)
    for key in ("name","description","scenario_type","priority","requirement_module_ids"): setattr(row,key,getattr(data,key))
    row.revision+=1; row.version+=1; row.status="draft" if row.status=="confirmed" else row.status
    await db.execute(delete(ScenarioStep).where(ScenarioStep.scenario_id==row.id))
    for step in data.steps: db.add(ScenarioStep(project_id=project_id,scenario_id=row.id,**step.model_dump()))
    await db.commit(); return await get(db,project_id,user,row.id)

async def confirm(db,project_id,user,scenario_id,revision:int):
    await require_membership(db,project_id,user); row=await db.scalar(select(TestScenario).where(TestScenario.id==scenario_id,TestScenario.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","场景不存在",404)
    if row.revision!=revision: raise AppError("REVISION_CONFLICT","场景已被修改",409,{"current_revision":row.revision})
    steps=(await db.scalars(select(ScenarioStep).where(ScenarioStep.scenario_id==row.id))).all()
    if not steps: raise AppError("SCENARIO_STEPS_REQUIRED","场景至少包含一个步骤",422)
    row.status="confirmed"; row.confirmed_by=user.id; row.confirmed_at=datetime.now(UTC); row.revision+=1
    coverages=(await db.scalars(select(RequirementCoverage).where(
        RequirementCoverage.project_id==project_id,RequirementCoverage.scenario_type=="api",
        RequirementCoverage.scenario_id==row.id))).all()
    for coverage in coverages:
        coverage.status="CONFIRMED"; coverage.revision+=1
    await db.commit(); return await get(db,project_id,user,row.id)
