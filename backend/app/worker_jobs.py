from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import UTC,datetime
from pathlib import Path
from sqlalchemy import func,select
from app.config import get_settings
from app.database import worker_db_session
from app.models import ApiInterface,ContentBlock,DocumentParseJob,DocumentVersion,ExecutionStep,ExecutionTask,Project,ReportStep,RequirementModule,TestReport,User
from app.services.documents import parse_document,suggest_modules
from app.services.events import publish_execution
from app.services.http_execution import execute_request
from app.services.masking import mask_data
from app.services.request_engine import apply_request_override,compose_request

def parse_document_job(version_id:str)->None: asyncio.run(_parse_document(version_id))

async def _parse_document(version_id:str)->None:
    settings=get_settings()
    async with worker_db_session() as db:
        version=await db.get(DocumentVersion,version_id)
        if not version: return
        job=await db.scalar(select(DocumentParseJob).where(DocumentParseJob.document_version_id==version.id))
        if not job or job.status=="completed": return
        job.status="running"; job.progress=5; job.started_at=datetime.now(UTC); version.parse_status="running"; await db.commit()
        try:
            if job.cancel_requested: job.status=version.parse_status="canceled"; job.finished_at=datetime.now(UTC); await db.commit(); return
            content=(settings.upload_root/version.object_key).read_bytes()
            blocks=await asyncio.wait_for(asyncio.to_thread(parse_document,version.file_name,content,settings.max_pdf_pages,settings.max_docx_images),timeout=settings.document_parse_timeout_seconds)
            for block in blocks: db.add(ContentBlock(project_id=version.project_id,document_version_id=version.id,**block))
            await db.flush()
            persisted=(await db.scalars(select(ContentBlock).where(ContentBlock.document_version_id==version.id).order_by(ContentBlock.seq))).all()
            by_seq={b.seq:b.id for b in persisted}
            for candidate in suggest_modules(blocks):
                db.add(RequirementModule(project_id=version.project_id,document_version_id=version.id,name=candidate["name"],description=candidate["description"],source_block_ids=[by_seq[seq] for seq in candidate["source_seqs"] if seq in by_seq]))
            job.status="completed"; job.progress=100; job.finished_at=datetime.now(UTC); version.parse_status="completed"; await db.commit()
        except Exception as exc:
            await db.rollback(); version=await db.get(DocumentVersion,version_id); job=await db.scalar(select(DocumentParseJob).where(DocumentParseJob.document_version_id==version_id))
            if version and job: version.parse_status="failed"; version.parse_error=str(exc)[:1000]; job.status="failed"; job.error_code=getattr(exc,"code","DOCUMENT_PARSE_FAILED"); job.error_message=str(exc)[:1000]; job.finished_at=datetime.now(UTC); await db.commit()

def execute_scenario_job(execution_id:str)->None:
    try:
        asyncio.run(_execute_scenario(execution_id))
    except Exception as exc:
        asyncio.run(_mark_execution_failed(execution_id,exc))
        raise


async def _mark_execution_failed(execution_id:str,exc:Exception)->None:
    async with worker_db_session() as db:
        task=await db.get(ExecutionTask,execution_id)
        if not task or task.status in {"completed","failed","canceled"}: return
        task.status="failed"; task.error_category="executor_error"; task.error_message=str(exc)[:1000]; task.finished_at=datetime.now(UTC); await db.commit(); await _ensure_report(db,task); publish_execution(task.id,{"type":"execution_update","version":task.event_version,"data":{"status":"failed","error_category":"executor_error"}})

def error_category(exc:Exception)->str:
    code=getattr(exc,"code","")
    return {"VARIABLE_MISSING":"variable_missing","SECRET_NOT_CONFIGURED":"authentication_failed","EXECUTION_TIMEOUT":"timeout","REQUEST_FAILED":"request_failed","RESPONSE_TOO_LARGE":"request_failed"}.get(code,"executor_error")

async def _emit(db,task,event_type:str,payload:dict):
    task.event_version+=1; await db.commit(); publish_execution(task.id,{"type":event_type,"version":task.event_version,"data":payload})

async def _execute_scenario(execution_id:str)->None:
    async with worker_db_session() as db:
        task=await db.get(ExecutionTask,execution_id)
        if not task or task.status in {"completed","failed","canceled"}: return
        existing=(await db.scalars(select(ExecutionStep).where(ExecutionStep.execution_id==task.id).order_by(ExecutionStep.seq))).all()
        if any(step.status=="running" for step in existing):
            for step in existing:
                if step.status=="running": step.status="error"; step.error_category="executor_error"; step.error_message="Worker 重启后未重放已开始步骤"; step.finished_at=datetime.now(UTC)
            task.status="failed"; task.error_category="executor_error"; task.error_message="检测到未完成的运行步骤，已安全终止"; task.finished_at=datetime.now(UTC); await db.commit(); await _ensure_report(db,task); publish_execution(task.id,{"type":"execution_update","version":task.event_version,"data":{"status":task.status}}); return
        task.status="running"; task.started_at=task.started_at or datetime.now(UTC); await _emit(db,task,"execution_update",{"status":"running"})
        runtime_vars={}; scenario_cookies:dict[str,str]={}; failed=False
        for step_cfg in task.scenario_snapshot.get("steps",[]):
            await db.refresh(task)
            if task.cancel_requested:
                task.status="canceled"; task.finished_at=datetime.now(UTC); break
            prior=next((s for s in existing if s.seq==step_cfg["seq"]),None)
            if prior and prior.status in {"passed","failed","error","skipped","canceled"}: continue
            interface=await db.get(ApiInterface,step_cfg.get("interface_id")) if step_cfg.get("interface_id") else None
            if not interface or interface.project_id!=task.project_id:
                await _save_error_step(db,task,step_cfg,"executor_error","接口资产不存在"); failed=True; break
            manual=interface.manual_config or {}; request={"method":interface.method,"url":interface.path,"headers":manual.get("headers",{}),"params":manual.get("params",{}),"cookies":manual.get("cookies",{}),"body_type":manual.get("body_type","none"),"body":manual.get("body"),"auth":manual.get("auth",{}),"variables":manual.get("variables",{}),"extracts":step_cfg.get("extracts") or manual.get("extracts",[]),"assertions":step_cfg.get("assertions") or manual.get("assertions",[])}
            request=apply_request_override(request,step_cfg.get("request_override"))
            step=ExecutionStep(project_id=task.project_id,execution_id=task.id,seq=step_cfg["seq"],name=step_cfg["name"],status="running",started_at=datetime.now(UTC)); db.add(step); await db.flush(); await _emit(db,task,"step_update",{"seq":step.seq,"status":"running"})
            try:
                execution_env={**task.environment_snapshot,"variables":{**(task.environment_snapshot.get("variables") or {}),**(task.environment_snapshot.get("secret_refs") or {})}}
                composed=compose_request(request,execution_env,[runtime_vars])
                step.request_snapshot=composed["preview"]
                attempts=1+(step_cfg.get("retry_count",0) if interface.method in {"GET","HEAD","OPTIONS"} else 0); result=None
                for attempt in range(attempts):
                    try: result=await execute_request(composed["request"],connect_timeout_ms=min(step_cfg.get("timeout_ms",30000),5000),read_timeout_ms=step_cfg.get("timeout_ms",30000),total_timeout_ms=step_cfg.get("timeout_ms",30000),known_secrets=composed["sensitive_values"],cookie_jar=scenario_cookies); break
                    except Exception:
                        if attempt+1>=attempts: raise
                runtime_vars.update(result["runtime_extracted"]); step.status=result["status"]; step.response_snapshot=result["response"]; step.extracted=result["extracted"]; step.assertions=result["assertions"]; step.error_category=result["error_category"]; step.error_message=result["error_message"]; failed=step.status!="passed"
            except Exception as exc:
                step.status="error"; step.error_category=error_category(exc); step.error_message=str(getattr(exc,"message",exc))[:1000]; failed=True
            step.finished_at=datetime.now(UTC); step.duration_ms=max(0,int((step.finished_at-step.started_at).total_seconds()*1000)); await _emit(db,task,"step_update",{"seq":step.seq,"status":step.status,"duration_ms":step.duration_ms,"error_category":step.error_category})
            if failed and not step_cfg.get("continue_on_failure"): break
        if task.status!="canceled": task.status="failed" if failed else "completed"; task.finished_at=datetime.now(UTC)
        finished_seqs=set((await db.scalars(select(ExecutionStep.seq).where(ExecutionStep.execution_id==task.id))).all())
        terminal_status="canceled" if task.status=="canceled" else "skipped"
        for cfg in task.scenario_snapshot.get("steps",[]):
            if cfg["seq"] not in finished_seqs:
                db.add(ExecutionStep(project_id=task.project_id,execution_id=task.id,seq=cfg["seq"],name=cfg["name"],status=terminal_status,error_message="任务已取消" if terminal_status=="canceled" else "前序步骤失败，未继续执行"))
        await db.commit(); await _ensure_report(db,task); await _emit(db,task,"execution_update",{"status":task.status,"finished_at":task.finished_at.isoformat()})

async def _save_error_step(db,task,cfg,category,message):
    now=datetime.now(UTC); step=ExecutionStep(project_id=task.project_id,execution_id=task.id,seq=cfg["seq"],name=cfg["name"],status="error",started_at=now,finished_at=now,error_category=category,error_message=message); db.add(step); await db.commit()

async def _ensure_report(db,task):
    report=await db.scalar(select(TestReport).where(TestReport.execution_id==task.id))
    if report: return report
    steps=(await db.scalars(select(ExecutionStep).where(ExecutionStep.execution_id==task.id).order_by(ExecutionStep.seq))).all(); project=await db.get(Project,task.project_id); user=await db.get(User,task.created_by)
    module_ids=task.scenario_snapshot.get("requirement_module_ids") or []; modules=(await db.scalars(select(RequirementModule).where(RequirementModule.id.in_(module_ids)))).all() if module_ids else []
    counts={status:sum(1 for step in steps if step.status==status) for status in ("passed","failed","error","skipped","canceled")}; status="passed" if task.status=="completed" else task.status
    report=TestReport(project_id=task.project_id,execution_id=task.id,status=status,summary={**counts,"total":len(steps),"duration_ms":sum(s.duration_ms for s in steps)},project_snapshot={"id":project.id,"name":project.name},environment_snapshot=mask_data(deepcopy(task.environment_snapshot)),scenario_snapshot=deepcopy(task.scenario_snapshot),requirement_snapshot=[{"id":m.id,"name":m.name,"document_version_id":m.document_version_id,"revision":m.revision} for m in modules],triggered_by_snapshot={"id":user.id,"username":user.username,"name":user.name},started_at=task.started_at,finished_at=task.finished_at); db.add(report); await db.flush()
    for s in steps: db.add(ReportStep(project_id=task.project_id,report_id=report.id,seq=s.seq,name=s.name,status=s.status,duration_ms=s.duration_ms,request_snapshot=deepcopy(s.request_snapshot),response_snapshot=deepcopy(s.response_snapshot),extracted=deepcopy(s.extracted),assertions=deepcopy(s.assertions),error_category=s.error_category,error_message=s.error_message,repro_steps=[f"第 {s.seq} 步：{s.name}",f"{s.request_snapshot.get('method','')} {s.request_snapshot.get('url','')}","按脱敏请求参数重放并核对断言"]));
    await db.commit(); return report
