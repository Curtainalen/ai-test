from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import UTC,datetime
from pathlib import Path
from sqlalchemy import func,select
from app.config import get_settings
from app.database import worker_db_session
from app.models import ApiInterface,ContentBlock,DocumentImage,DocumentParseJob,DocumentVersion,ExecutionStep,ExecutionTask,ModelConfig,Project,ReportStep,RequirementCoverage,RequirementDataItem,RequirementDocument,RequirementModule,RequirementModuleSplitJob,TestReport,User
from app.services.documents import module_split_response_schema,parse_document,suggest_modules
from app.services.documents import ai_module_candidates, validate_module_candidates
from app.services.events import publish_execution
from app.services.http_execution import execute_request
from app.services.masking import mask_data
from app.services.request_engine import apply_request_override,compose_request
from app.services.llm import DefaultLlmGateway
from app.services import requirement_assets
import json
from app.security import decrypt_bytes, encrypt_secret
from app.services.sensitive import sanitize_block, serialized_raw_block

def parse_document_job(version_id:str)->None: asyncio.run(_parse_document(version_id))
def split_requirement_modules_job(job_id:str)->None: asyncio.run(_split_requirement_modules(job_id))

async def _split_requirement_modules(job_id: str) -> None:
    async with worker_db_session() as db:
        try:
            # 模块拆分是独立异步任务，解析必须完成且正文已确认后才能执行。
            job=await db.get(RequirementModuleSplitJob, job_id)
            if not job or job.status not in {"pending", "running"}: return
            job.status="running"; await db.commit()
            version=await db.get(DocumentVersion, job.document_version_id)
            document=await db.get(RequirementDocument, version.document_id) if version else None
            user=await db.get(User, job.created_by)
            if not version or not document or not user or version.parse_status != "completed" or version.content_status != "confirmed":
                job.status, job.error_code, job.error_message="failed", "DOCUMENT_NOT_PARSED", "文档尚未解析完成"
                await db.commit(); return
            blocks=(await db.scalars(select(ContentBlock).where(ContentBlock.document_version_id == version.id).order_by(ContentBlock.seq))).all()
            raw=[requirement_assets.block_view(block) for block in blocks]
            candidates=None; fallback=False; coverage_report={}
            config=await db.scalar(select(ModelConfig).where(ModelConfig.is_enabled.is_(True), ModelConfig.is_default.is_(True)))
            try:
                if not config: raise RuntimeError("MODEL_CONFIG_NOT_FOUND")
                schema=module_split_response_schema()
                source=[{"seq": block.seq, "type": block.block_type, "content": block.content} for block in blocks]
                result=await DefaultLlmGateway(db).generate(project_id=job.project_id, model_config_id=config.id, created_by=user.id, purpose="requirement_module_split", timeout_ms=min(config.timeout_seconds * 1000, 120000), response_schema=schema, prompt="仅根据以下当前需求文档内容拆分需求模块。不得引用未提供内容；输出必须严格遵循 JSON Schema。\n" + json.dumps(source, ensure_ascii=False))
                candidates=ai_module_candidates(result.data, raw)
                candidates, coverage_report = validate_module_candidates(candidates, raw)
                # Keep valid AI modules; repair only uncovered/invalid regions with deterministic boundaries.
                if coverage_report.get("uncovered_blocks") or coverage_report.get("empty_modules") or coverage_report.get("invalid_blocks"):
                    valid_seqs=set(seq for item in candidates for seq in item.get("source_seqs", []))
                    repairs=[item for item in suggest_modules(raw) if set(item.get("source_seqs", [])) - valid_seqs]
                    for item in repairs:
                        item["split_method"]="rule_fallback"; item["status"]="ai_repaired"
                    candidates.extend(repairs)
                    coverage_report["module_status"].update({item["name"]: "ai_repaired" for item in repairs})
                    coverage_report["repair_applied"] = bool(repairs)
            except Exception as exc:
                job.error_code=getattr(exc, "code", "AI_MODULE_SPLIT_INVALID_OUTPUT")
                job.error_message=str(getattr(exc, "message", exc))[:1000]
                candidates=suggest_modules(raw)
                for candidate in candidates: candidate["split_method"]="rule_fallback"; candidate["status"]="rule_fallback"
                _, coverage_report = validate_module_candidates(candidates, raw)
                fallback=True
            job.coverage_report=coverage_report
            await requirement_assets._persist_split_candidates(db, job.project_id, user, document, version, "ai", candidates, fallback, job)
        except Exception as exc:
            await db.rollback()
            job=await db.get(RequirementModuleSplitJob, job_id)
            if job:
                job.status, job.error_code, job.error_message="failed", getattr(exc, "code", "MODULE_SPLIT_FAILED"), "需求模块拆分失败"
                await db.commit()

async def _parse_document(version_id:str)->None:
    settings=get_settings()
    async with worker_db_session() as db:
        version=await db.get(DocumentVersion,version_id)
        if not version: return
        job=await db.scalar(select(DocumentParseJob).where(DocumentParseJob.document_version_id==version.id))
        if not job or job.status=="completed": return
        # Worker 负责耗时解析，API 请求只创建任务并立即返回，避免阻塞用户操作。
        job.status="running"; job.progress=5; job.started_at=datetime.now(UTC); version.parse_status="running"; await db.commit()
        try:
            if job.cancel_requested: job.status=version.parse_status="canceled"; job.finished_at=datetime.now(UTC); await db.commit(); return
            stored_content=(settings.upload_root/version.object_key).read_bytes()
            # 新版本文件是密文；兼容旧版本明文文件，避免历史文档无法重新解析。
            content=decrypt_bytes(stored_content) if getattr(version, "storage_encrypted", False) else stored_content
            # 将同步解析器放入线程，并设置总超时，防止大文件或损坏文件长期占用 Worker。
            blocks=await asyncio.wait_for(asyncio.to_thread(parse_document,version.file_name,content,settings.max_pdf_pages,settings.max_docx_images),timeout=settings.document_parse_timeout_seconds)
            full_text=[]
            # 用引用作为唯一键，避免同一文档多处出现“密码/Token”时重复创建数据项。
            parsed_items={}
            # 重试时先清理本版本旧的中间结果，保证内容块和数据目录不会重复。
            from sqlalchemy import delete
            await db.execute(delete(ContentBlock).where(ContentBlock.document_version_id == version.id))
            await db.execute(delete(RequirementDataItem).where(RequirementDataItem.document_version_id == version.id))
            for block in blocks:
                # 深拷贝原始结构，避免后续移除临时图片字节时破坏密文备份内容。
                original_block = deepcopy(block)
                structured=dict(block.get("structured_content") or {})
                # 脱敏正文用于页面和 AI；原始正文只通过密文列保存。
                safe_block, items = sanitize_block(block)
                image_bytes=structured.pop("_image_bytes", None)
                if image_bytes is not None:
                    # 图片按文档版本隔离存储，内容块仅保留可审计的图片标识和元数据。
                    image_id=structured["image_id"]
                    suffix={"image/png":"png", "image/jpeg":"jpg", "image/gif":"gif", "image/bmp":"bmp", "image/tiff":"tiff"}.get(structured.get("mime_type"), "bin")
                    object_key=f"{version.project_id}/{version.document_id}/{version.version}/images/{image_id}.{suffix}"
                    target=settings.upload_root/object_key; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(encrypt_bytes(image_bytes))
                    db.add(DocumentImage(project_id=version.project_id, document_version_id=version.id, image_id=image_id, object_key=object_key, mime_type=structured.get("mime_type", "application/octet-stream"), file_size=len(image_bytes), sort_order=block["seq"], storage_encrypted=True))
                safe_structured = dict(safe_block.get("structured_content") or {})
                # 图片字节只允许短暂存在于 Worker 内存，绝不能进入 JSON 字段。
                safe_structured.pop("_image_bytes", None)
                safe_block["structured_content"] = safe_structured or structured
                safe_block["raw_content_ciphertext"] = encrypt_secret(original_block.get("content", ""))
                # 原始结构化元数据需要保留，但图片二进制已单独存储，不能重复写入数据库密文。
                raw_structured = dict(original_block.get("structured_content") or {})
                raw_structured.pop("_image_bytes", None)
                original_for_storage = dict(original_block)
                original_for_storage["structured_content"] = raw_structured
                safe_block["raw_structured_content_ciphertext"] = encrypt_secret(serialized_raw_block(original_for_storage))
                # 解析器的统一输出在这里落库；同时保存完整全文，供人工核对和来源追溯。
                db.add(ContentBlock(project_id=version.project_id,document_version_id=version.id,**safe_block))
                if safe_block["content"]: full_text.append(safe_block["content"])
                for item in items:
                    key = item["reference"]
                    if key in parsed_items:
                        parsed_items[key]["source_block_ids"] = list(dict.fromkeys(
                            parsed_items[key].get("source_block_ids", []) + [item.get("source_block_seq")]
                        ))
                    else:
                        # 首次发现也要记录来源序号，后续重复出现时才能完整聚合来源块。
                        item["source_block_ids"] = [item.get("source_block_seq")]
                        parsed_items[key] = item
            await db.flush()
            block_ids = {row.seq: row.id for row in (await db.scalars(select(ContentBlock).where(ContentBlock.document_version_id == version.id))).all()}
            for item in parsed_items.values():
                source_seqs = item.pop("source_block_ids", []) or [item.get("source_block_seq")]
                item["source_block_ids"] = [block_ids[seq] for seq in source_seqs if seq in block_ids]
                db.add(RequirementDataItem(project_id=version.project_id, document_version_id=version.id, **item))
            # 解析只生成可核对的全文；模块拆分仍必须由用户在确认全文后主动发起。
            version.full_text="\n\n".join(full_text)
            job.status="completed"; job.progress=100; job.finished_at=datetime.now(UTC); version.parse_status="completed"; version.parse_error=None; await db.commit()
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
    coverages=(await db.scalars(select(RequirementCoverage).where(
        RequirementCoverage.project_id==task.project_id,RequirementCoverage.scenario_type=="api",
        RequirementCoverage.scenario_id==task.scenario_id))).all()
    coverage_status="PASSED" if task.status=="completed" else "FAILED"
    for coverage in coverages:
        coverage.status=coverage_status; coverage.execution_report_id=report.id; coverage.revision+=1
    await db.commit(); return report
