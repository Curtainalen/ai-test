from __future__ import annotations
from datetime import UTC,datetime
import json
from pathlib import Path
from sqlalchemy import func,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.errors import AppError
from app.models import ContentBlock,DocumentImage,DocumentParseJob,DocumentVersion,ModelConfig,RequirementDataItem,RequirementDocument,RequirementModule,RequirementModuleSplitJob,RequirementReview,RequirementTestCase,RequirementTestPoint,RequirementCoverage,TestScenario,User
from app.services.documents import ALLOWED,ai_module_candidates,decode_text,sha256_bytes,suggest_modules,validate_filename
from app.services.identity import require_membership
from app.services.llm import DefaultLlmGateway
from app.services.queue import enqueue_unique
from app.security import decrypt_bytes, encrypt_bytes, decrypt_secret
from app.services.sensitive import contains_suspected_secret

def version_view(v,job=None): return {"id":v.id,"document_id":v.document_id,"version":v.version,"file_name":v.file_name,"mime_type":v.mime_type,"file_size":v.file_size,"sha256":v.sha256,"parse_status":v.parse_status,"parse_error":v.parse_error,"content_status":getattr(v, "content_status", "pending_confirmation"),"content_confirmed_at":v.content_confirmed_at.isoformat() if getattr(v, "content_confirmed_at", None) else None,"full_text":getattr(v, "full_text", ""),"job":({"id":job.id,"status":job.status,"progress":job.progress,"error_code":job.error_code,"error_message":job.error_message} if job else None),"created_at":v.created_at.isoformat()}
def block_view(b):
    # 默认返回脱敏正文；原始正文必须通过单独的显式原文接口读取。
    return {"id":b.id,"seq":b.seq,"block_type":b.block_type,"content":b.content,"structured_content":b.structured_content,"source_locator":b.source_locator,"confidence":b.confidence,"needs_correction":b.needs_correction,"sensitive_spans":getattr(b, "sensitive_spans", []) or [],"parse_warnings":getattr(b, "parse_warnings", []) or [],"raw_available":bool(getattr(b, "raw_content_ciphertext", None))}


def data_item_view(item):
    """数据目录只返回引用和掩码预览，绝不返回真实值。"""
    sensitivity = "secret" if item.sensitive else "internal"
    return {"id": item.id, "name": item.name, "label": item.name, "data_type": item.data_type,
            "reference": item.value_ref, "sensitivity": sensitivity,
            "preview": "***" if item.sensitive else item.preview,
            "source_block_seq": item.source_block_seq, "source_block_ids": [],
            "constraints": {}, "status": item.status}

def extract_requirement_data(blocks):
    """从正文中提取测试数据引用候选；这里只保存引用，不保存真实敏感值。"""
    import re
    items=[]; seen=set()
    patterns=[("password", "secret", True), ("token", "runtime", True), ("username", "string", False), ("用户名", "string", False), ("密码", "secret", True), ("账号", "string", False)]
    for block in blocks:
        text=block.content or ""
        for label, kind, sensitive in patterns:
            if label.lower() not in text.lower(): continue
            name={"password":"login_password","密码":"login_password","username":"login_username","用户名":"login_username","账号":"login_username","token":"access_token"}[label]
            if name in seen: continue
            seen.add(name); ref=f"secret://{name}" if sensitive else f"secret://{name}"
            items.append({"name":name,"data_type":kind,"value_ref":ref,"preview":"***" if sensitive else "待配置","sensitive":sensitive,"source_block_seq":block.seq,"status":"pending_confirmation"})
    return items

async def get_document_image(db, project_id, user, document_id, version_id, image_id):
    await require_membership(db, project_id, user)
    row=await db.scalar(select(DocumentImage).join(DocumentVersion, DocumentVersion.id == DocumentImage.document_version_id).where(DocumentImage.project_id==project_id, DocumentImage.document_version_id==version_id, DocumentImage.image_id==image_id, DocumentVersion.document_id==document_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND", "文档图片不存在", 404)
    target=get_settings().upload_root / row.object_key
    if not target.is_file(): raise AppError("DOCUMENT_IMAGE_MISSING", "文档图片文件不存在", 404)
    # 新图片为密文文件，读取时在内存中解密，不生成长期明文副本。
    return (decrypt_bytes(target.read_bytes()) if getattr(row, "storage_encrypted", False) else target.read_bytes()), row.mime_type

async def get_original_document(db, project_id, user, document_id, version_id):
    await require_membership(db, project_id, user)
    row=await db.scalar(select(DocumentVersion).where(DocumentVersion.id==version_id, DocumentVersion.document_id==document_id, DocumentVersion.project_id==project_id))
    if not row: raise AppError("INVALID_DOCUMENT_VERSION", "文档版本不属于当前需求文档", 422)
    target=get_settings().upload_root / row.object_key
    if not target.is_file(): raise AppError("DOCUMENT_FILE_MISSING", "原始文档文件不存在", 404)
    # 原文是显式受控查看内容，只在内存中解密后由 API 返回。
    return (decrypt_bytes(target.read_bytes()) if getattr(row, "storage_encrypted", False) else target.read_bytes()), row.mime_type, row.file_name
def split_job_view(job): return {"id":job.id,"document_version_id":job.document_version_id,"method":job.method,"status":job.status,"error_code":job.error_code,"error_message":job.error_message,"fallback_used":job.fallback_used,"coverage_report":getattr(job, "coverage_report", {}) or {}}
def module_view(m, coverage_count=0): return {"id":m.id,"name":m.name,"description":m.description,"source_block_ids":m.source_block_ids,"source_type":getattr(m, "source_type", "content_blocks"),"sort_order":getattr(m, "sort_order", 0),"parent_module_id":getattr(m, "parent_module_id", None),"split_method":getattr(m, "split_method", "rule"),"confidence":getattr(m, "confidence", None),"status":m.status,"revision":m.revision,"document_version_id":m.document_version_id,"coverage_count":coverage_count,"archived_at":getattr(m, "archived_at", None).isoformat() if getattr(m, "archived_at", None) else None}

def document_list_view(document, version):
    return {"id":document.id,"title":document.title,"latest_version":version.version,"latest_version_id":version.id,
            "parse_status":version.parse_status,"content_status":getattr(version, "content_status", "pending_confirmation"),"file_name":version.file_name,"uploaded_at":version.created_at.isoformat()}

def source_preview(version: DocumentVersion) -> str | None:
    """只为历史兼容保留文本预览；解析完成后的默认页面使用脱敏 ContentBlock。"""
    if Path(version.file_name).suffix.lower() not in {".txt", ".md", ".markdown"}:
        return None
    try:
        raw = (get_settings().upload_root / version.object_key).read_bytes()
        if getattr(version, "storage_encrypted", False):
            raw = decrypt_bytes(raw)
        return decode_text(raw)[:200_000]
    except Exception:
        return None

async def list_modules(db,project_id,user,status:str|None=None):
    await require_membership(db,project_id,user)
    query=select(RequirementModule).where(RequirementModule.project_id==project_id)
    if status:
        query=query.where(RequirementModule.status==status)
    rows=(await db.scalars(query.order_by(RequirementModule.sort_order, RequirementModule.created_at))).all()
    return [module_view(row) for row in rows]

async def list_documents(db, project_id, user, page: int, page_size: int):
    await require_membership(db, project_id, user)
    total = await db.scalar(select(func.count()).select_from(RequirementDocument).where(RequirementDocument.project_id == project_id))
    latest_versions = select(
        DocumentVersion.document_id.label("document_id"),
        func.max(DocumentVersion.version).label("latest_version"),
    ).where(DocumentVersion.project_id == project_id).group_by(DocumentVersion.document_id).subquery()
    rows = list((await db.execute(
        select(RequirementDocument, DocumentVersion)
        .join(latest_versions, latest_versions.c.document_id == RequirementDocument.id)
        .join(DocumentVersion, (DocumentVersion.document_id == latest_versions.c.document_id) & (DocumentVersion.version == latest_versions.c.latest_version))
        .where(RequirementDocument.project_id == project_id)
        .order_by(DocumentVersion.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all())
    return {"items": [document_list_view(document, version) for document, version in rows], "page": page, "page_size": page_size, "total": total or 0}

async def create_upload(db:AsyncSession,project_id:str,user:User,filename:str,content_type:str,content:bytes,title:str|None=None,document_id:str|None=None):
    # 上传阶段只负责校验、保存版本并创建解析任务载体；文档版本本身不可覆盖修改。
    await require_membership(db,project_id,user); settings=get_settings(); safe,ext=validate_filename(filename)
    if len(content)>settings.max_upload_bytes: raise AppError("FILE_TOO_LARGE","文件超过大小限制",413,{"limit":settings.max_upload_bytes})
    expected=ALLOWED[ext]
    if content_type and content_type not in {expected,"application/octet-stream","text/plain" if ext in {'.md','.markdown'} else expected}: raise AppError("FILE_MIME_MISMATCH","文件扩展名与 MIME 不一致",422)
    if ext==".pdf" and not content.startswith(b"%PDF-"): raise AppError("FILE_CONTENT_MISMATCH","文件内容不是有效 PDF",422)
    if ext==".docx" and not content.startswith(b"PK"): raise AppError("FILE_CONTENT_MISMATCH","文件内容不是有效 DOCX",422)
    digest=sha256_bytes(content)
    duplicate=await db.scalar(select(DocumentVersion).where(DocumentVersion.project_id==project_id,DocumentVersion.sha256==digest))
    if duplicate: raise AppError("FILE_DUPLICATE","相同文件已上传",409,{"document_version_id":duplicate.id})
    if document_id:
        document=await db.scalar(select(RequirementDocument).where(RequirementDocument.id==document_id,RequirementDocument.project_id==project_id))
        if not document: raise AppError("RESOURCE_NOT_FOUND","需求文档不存在",404)
        next_version=(await db.scalar(select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id==document.id)) or 0)+1
    else:
        document=RequirementDocument(project_id=project_id,title=title or Path(safe).stem,created_by=user.id); db.add(document); await db.flush(); next_version=1
    # 原始文件按项目、文档和版本隔离保存，便于后续审计、版本比较和权限校验。
    object_key=f"{project_id}/{document.id}/{next_version}-{digest[:12]}{ext}"; target=settings.upload_root/object_key; target.parent.mkdir(parents=True,exist_ok=True)
    # 原始文件只以密文落盘；明文 content 仅存在于当前请求内，随后立即释放。
    target.write_bytes(encrypt_bytes(content))
    version=DocumentVersion(project_id=project_id,document_id=document.id,version=next_version,file_name=safe,object_key=object_key,mime_type=expected,file_size=len(content),sha256=digest,storage_encrypted=True,parse_status="pending",content_status="pending_confirmation",uploaded_by=user.id)
    db.add(version); await db.flush()
    # 上传成功即创建解析任务，正文确认改为解析后的人工审核，而不是解析启动按钮。
    job=DocumentParseJob(project_id=project_id, document_version_id=version.id, status="pending")
    db.add(job); await db.flush()
    try: await db.commit()
    except IntegrityError as exc:
        await db.rollback(); target.unlink(missing_ok=True); raise AppError("FILE_DUPLICATE","相同文件已上传",409) from exc
    if next_version > 1:
        old_version_ids=list((await db.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id==document.id,DocumentVersion.id!=version.id))).all())
        if old_version_ids:
            modules=(await db.scalars(select(RequirementModule).where(RequirementModule.document_version_id.in_(old_version_ids),RequirementModule.status=="confirmed"))).all()
            for module in modules: module.status="needs_review"; module.revision+=1
            changed_ids={module.id for module in modules}
            if changed_ids:
                scenarios=(await db.scalars(select(TestScenario).where(TestScenario.project_id==project_id))).all()
                for scenario in scenarios:
                    if changed_ids.intersection(scenario.requirement_module_ids or []): scenario.status="needs_review"; scenario.revision+=1
            await db.commit()
    try:
        enqueue_unique("app.worker_jobs.parse_document_job", version.id, settings.document_parse_timeout_seconds + 30)
    except AppError:
        job.status, job.error_code, job.error_message = "failed", "QUEUE_UNAVAILABLE", "解析任务队列暂不可用"
        version.parse_status, version.parse_error = "failed", "解析任务队列暂不可用"
        await db.commit()
        raise
    return document,version,job

async def get_document(db,project_id,user,document_id,version_id: str | None = None):
    await require_membership(db,project_id,user)
    doc=await db.scalar(select(RequirementDocument).where(RequirementDocument.id==document_id,RequirementDocument.project_id==project_id))
    if not doc: raise AppError("RESOURCE_NOT_FOUND","需求文档不存在",404)
    versions=(await db.scalars(select(DocumentVersion).where(DocumentVersion.project_id==project_id,DocumentVersion.document_id==doc.id).order_by(DocumentVersion.version.desc()))).all()
    version=next((item for item in versions if item.id == version_id), None) if version_id else versions[0]
    if not version: raise AppError("INVALID_DOCUMENT_VERSION", "文档版本不属于当前需求文档", 422)
    job=await db.scalar(select(DocumentParseJob).where(DocumentParseJob.document_version_id==version.id))
    blocks=(await db.scalars(select(ContentBlock).where(ContentBlock.document_version_id==version.id).order_by(ContentBlock.seq))).all()
    modules=(await db.scalars(select(RequirementModule).where(RequirementModule.document_version_id==version.id).order_by(RequirementModule.sort_order, RequirementModule.created_at))).all()
    split_job=await db.scalar(select(RequirementModuleSplitJob).where(RequirementModuleSplitJob.document_version_id == version.id).order_by(RequirementModuleSplitJob.created_at.desc()))
    point_modules = select(RequirementReview.requirement_module_id).join(RequirementTestPoint, RequirementTestPoint.review_id == RequirementReview.id).where(RequirementReview.project_id == project_id).subquery()
    counts = dict((await db.execute(select(point_modules.c.requirement_module_id, func.count()).group_by(point_modules.c.requirement_module_id))).all())
    locators={block.id: block.source_locator for block in blocks}
    data=[module_view(m, counts.get(m.id, 0)) for m in modules]
    data_rows=(await db.scalars(select(RequirementDataItem).where(RequirementDataItem.project_id == project_id, RequirementDataItem.document_version_id == version.id).order_by(RequirementDataItem.created_at))).all()
    data_items=[data_item_view(item) for item in data_rows]
    for item in data: item["source_locators"]=[locators[block_id] for block_id in item["source_block_ids"] if block_id in locators]
    return {"id":doc.id,"title":doc.title,"selected_version_id":version.id,"source_preview":None,"versions":[version_view(v,job if v.id==version.id else None) for v in versions],"split_job":split_job_view(split_job) if split_job else None,"modules":data,"data_items":data_items}

async def list_content_blocks(db, project_id, user, document_id, version_id: str):
    await require_membership(db, project_id, user)
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id,
        DocumentVersion.document_id == document_id, DocumentVersion.project_id == project_id))
    if not version:
        raise AppError("INVALID_DOCUMENT_VERSION", "文档版本不属于当前需求文档", 422)
    blocks = (await db.scalars(select(ContentBlock).where(ContentBlock.project_id == project_id,
        ContentBlock.document_version_id == version.id).order_by(ContentBlock.seq))).all()
    return {"document_version_id": version.id, "items": [block_view(block) for block in blocks]}


async def get_raw_content_block(db, project_id, user, document_id, version_id, block_id):
    """显式查看单个内容块原文；密文只在服务端内存中解密。"""
    await require_membership(db, project_id, user)
    row = await db.scalar(select(ContentBlock).join(DocumentVersion, DocumentVersion.id == ContentBlock.document_version_id).where(
        ContentBlock.id == block_id, ContentBlock.project_id == project_id,
        ContentBlock.document_version_id == version_id, DocumentVersion.document_id == document_id))
    if not row or not row.raw_content_ciphertext:
        raise AppError("RAW_CONTENT_NOT_AVAILABLE", "原始内容不存在", 404)
    return decrypt_secret(row.raw_content_ciphertext)

async def document_impact(db, project_id, user, document_id, version_id: str):
    await require_membership(db, project_id, user)
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id,
        DocumentVersion.document_id == document_id, DocumentVersion.project_id == project_id))
    if not version:
        raise AppError("INVALID_DOCUMENT_VERSION", "文档版本不属于当前需求文档", 422)
    versions = (await db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id,
        DocumentVersion.project_id == project_id).order_by(DocumentVersion.version.desc()))).all()
    previous = next((item for item in versions if item.version < version.version), None)
    current = (await db.scalars(select(RequirementModule).where(RequirementModule.document_version_id == version.id))).all()
    prior = (await db.scalars(select(RequirementModule).where(RequirementModule.document_version_id == previous.id))).all() if previous else []
    prior_names = {item.name for item in prior}; current_names = {item.name for item in current}
    changed = [module_view(item) for item in prior if item.status == "needs_review"]
    return {"current_version": version.version, "previous_version": previous.version if previous else None,
        "added_modules": [module_view(item) for item in current if item.name not in prior_names],
        "removed_modules": [module_view(item) for item in prior if item.name not in current_names],
        "changed_modules": [module_view(item) for item in current if item.name in prior_names and any(old.name == item.name and old.status == "needs_review" for old in prior)],
        "needs_review_modules": changed}

async def update_content_block(db, project_id, user, block_id: str, data):
    # 校正内容块会改变模块输入，因此必须让已确认模块及其下游结果重新进入待复核状态。
    await require_membership(db, project_id, user)
    row = await db.scalar(select(ContentBlock).where(ContentBlock.id == block_id, ContentBlock.project_id == project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND", "内容块不存在", 404)
    # 校正后的正文必须继续保持脱敏边界，禁止通过人工编辑重新写入真实凭据。
    if contains_suspected_secret(data.content):
        raise AppError("CONTENT_BLOCK_SECRET_DETECTED", "正文包含疑似敏感明文，请改用 secret:// 或 data:// 引用", 422)
    row.content = data.content
    row.needs_correction = False
    version = await db.get(DocumentVersion, row.document_version_id)
    if version and version.content_status == "confirmed":
        version.content_status, version.content_confirmed_by, version.content_confirmed_at = "pending_confirmation", None, None
    modules = (await db.scalars(select(RequirementModule).where(RequirementModule.project_id == project_id,
        RequirementModule.document_version_id == row.document_version_id))).all()
    for module in modules:
        if row.id in (module.source_block_ids or []) and module.status == "confirmed":
            module.status, module.confirmed_by, module.confirmed_at = "changed", None, None
            module.revision += 1
            await _mark_module_dependents_for_review(db, project_id, module.id)
    await db.commit(); await db.refresh(row)
    return block_view(row)


async def list_data_items(db, project_id, user, document_id, version_id):
    """返回当前文档版本的数据引用候选，前端可据此完成逐项确认。"""
    await require_membership(db, project_id, user)
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id,
        DocumentVersion.project_id == project_id, DocumentVersion.document_id == document_id))
    if not version:
        raise AppError("INVALID_DOCUMENT_VERSION", "文档版本不属于当前需求文档", 422)
    rows = (await db.scalars(select(RequirementDataItem).where(RequirementDataItem.project_id == project_id,
        RequirementDataItem.document_version_id == version.id).order_by(RequirementDataItem.created_at))).all()
    return {"document_version_id": version.id, "items": [data_item_view(row) for row in rows]}


async def update_data_item(db, project_id, user, item_id, data):
    """人工调整候选引用；引用协议必须与敏感级别一致。"""
    await require_membership(db, project_id, user)
    row = await db.scalar(select(RequirementDataItem).where(RequirementDataItem.id == item_id,
        RequirementDataItem.project_id == project_id))
    if not row:
        raise AppError("RESOURCE_NOT_FOUND", "需求数据项不存在", 404)
    expected_prefix = "secret://" if data.sensitivity == "secret" else "data://"
    if not data.reference.startswith(expected_prefix):
        raise AppError("DATA_REFERENCE_INVALID", f"{data.sensitivity} 数据必须使用 {expected_prefix} 引用", 422)
    # 修改映射会使全文再次待确认，避免用户在映射变化后直接沿用旧确认结果。
    row.name, row.data_type = data.name, data.data_type
    row.value_ref = data.reference
    row.sensitive = data.sensitivity == "secret"
    row.status = "pending_confirmation"
    version = await db.get(DocumentVersion, row.document_version_id)
    if version and version.content_status == "confirmed":
        version.content_status, version.content_confirmed_by, version.content_confirmed_at = "pending_confirmation", None, None
    await db.commit(); await db.refresh(row)
    return data_item_view(row)


async def decide_data_item(db, project_id, user, item_id, decision):
    """确认后才能把数据引用提供给后续 AI 和自动化流程。"""
    await require_membership(db, project_id, user)
    row = await db.scalar(select(RequirementDataItem).where(RequirementDataItem.id == item_id,
        RequirementDataItem.project_id == project_id))
    if not row:
        raise AppError("RESOURCE_NOT_FOUND", "需求数据项不存在", 404)
    row.status = decision
    version = await db.get(DocumentVersion, row.document_version_id)
    if version and version.content_status == "confirmed":
        version.content_status, version.content_confirmed_by, version.content_confirmed_at = "pending_confirmation", None, None
    await db.commit(); await db.refresh(row)
    return data_item_view(row)

async def confirm_document_content(db, project_id, user, document_id, document_version_id):
    # 正文确认是后续模块拆分的门禁；确认前必须确保当前版本已经解析完成。
    await require_membership(db, project_id, user)
    document = await db.scalar(select(RequirementDocument).where(RequirementDocument.id == document_id, RequirementDocument.project_id == project_id))
    if not document: raise AppError("RESOURCE_NOT_FOUND", "需求文档不存在", 404)
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.id == document_version_id, DocumentVersion.document_id == document.id, DocumentVersion.project_id == project_id))
    if not version: raise AppError("INVALID_DOCUMENT_VERSION", "文档版本不属于当前需求文档", 422)
    job = await db.scalar(select(DocumentParseJob).where(DocumentParseJob.document_version_id == version.id))
    if version.content_status == "confirmed":
        return {"document_id": document.id, "version": version_view(version, job)}
    if version.parse_status == "running":
        raise AppError("DOCUMENT_PARSE_IN_PROGRESS", "文档正在解析中", 409)
    if version.parse_status != "completed":
        raise AppError("DOCUMENT_NOT_PARSED", "请等待文档解析完成后再确认正文", 409)
    blocks = (await db.scalars(select(ContentBlock).where(ContentBlock.document_version_id == version.id))).all()
    unresolved_blocks = [block.seq for block in blocks if block.needs_correction]
    items = (await db.scalars(select(RequirementDataItem).where(RequirementDataItem.document_version_id == version.id))).all()
    unresolved_items = [item.name for item in items if item.status != "confirmed"]
    # 低置信度 OCR/图片块和敏感引用都由人工确认，防止未经审核的输入流入 AI。
    if unresolved_blocks or unresolved_items:
        raise AppError("DOCUMENT_CONTENT_REVIEW_REQUIRED", "请先校正低置信度正文并确认敏感数据引用", 409,
                       {"block_sequences": unresolved_blocks, "data_items": unresolved_items})
    version.content_status, version.content_confirmed_by, version.content_confirmed_at = "confirmed", user.id, datetime.now(UTC)
    await db.commit(); await db.refresh(version)
    return {"document_id": document.id, "version": version_view(version, job)}

async def create_module(db, project_id, user, data):
    # 手工模块也必须绑定一个已解析、已确认的文档版本，避免绕过正文审核流程。
    await require_membership(db, project_id, user)
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.id == data.document_version_id, DocumentVersion.project_id == project_id))
    if not version: raise AppError("INVALID_DOCUMENT_VERSION", "文档版本不属于当前项目", 422)
    if version.parse_status != "completed" or version.content_status != "confirmed": raise AppError("DOCUMENT_CONTENT_NOT_CONFIRMED", "请先确认原始需求全文并等待解析完成", 409)
    await _validate_module_source(db, project_id, version.id, data.source_block_ids, data.source_type)
    order = int(await db.scalar(select(func.max(RequirementModule.sort_order)).where(RequirementModule.document_version_id == version.id)) or 0) + 1
    row = RequirementModule(project_id=project_id, document_version_id=version.id, name=data.name, description=data.description, source_block_ids=data.source_block_ids, source_type=data.source_type, split_method="manual", sort_order=order, created_by=user.id, updated_by=user.id)
    db.add(row); await db.commit(); await db.refresh(row)
    return row

async def delete_module(db, project_id, user, module_id: str):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(RequirementModule).where(RequirementModule.id == module_id, RequirementModule.project_id == project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND", "需求模块不存在", 404)
    referenced = await _module_has_dependents(db, project_id, row.id)
    if referenced:
        row.status, row.archived_at, row.updated_by, row.revision = "archived", datetime.now(UTC), user.id, row.revision + 1
        outcome = "archived"
    else:
        await db.delete(row)
        outcome = "deleted"
    await db.commit()
    return outcome

async def _validate_module_source(db, project_id, version_id, source_block_ids, source_type):
    if source_type == "manual":
        if source_block_ids: raise AppError("INVALID_MANUAL_SOURCE", "人工模块不能关联内容块", 422)
        return
    if not source_block_ids: raise AppError("MODULE_SOURCE_REQUIRED", "模块必须关联来源内容块或标记为人工创建", 422)
    valid = set((await db.scalars(select(ContentBlock.id).where(ContentBlock.project_id == project_id, ContentBlock.document_version_id == version_id))).all())
    if not set(source_block_ids) <= valid: raise AppError("INVALID_SOURCE_BLOCK", "来源内容块不属于该文档版本", 422)

async def _module_is_referenced(db, project_id, module_id):
    scenarios=(await db.scalars(select(TestScenario.requirement_module_ids).where(TestScenario.project_id == project_id))).all()
    return any(module_id in (ids or []) for ids in scenarios)

async def _module_has_dependents(db, project_id, module_id):
    if await _module_is_referenced(db, project_id, module_id):
        return True
    return bool(await db.scalar(select(RequirementReview.id).where(
        RequirementReview.project_id == project_id,
        RequirementReview.requirement_module_id == module_id,
    )))

async def _mark_module_dependents_for_review(db, project_id, module_id):
    point_ids=select(RequirementTestPoint.id).join(RequirementReview,RequirementReview.id==RequirementTestPoint.review_id).where(RequirementTestPoint.project_id==project_id, RequirementReview.project_id==project_id, RequirementReview.requirement_module_id==module_id)
    await db.execute(update(RequirementCoverage).where(RequirementCoverage.project_id==project_id, RequirementCoverage.test_point_id.in_(point_ids)).values(status="NEEDS_REVIEW",revision=RequirementCoverage.revision+1))
    await db.execute(update(RequirementReview).where(RequirementReview.project_id==project_id,RequirementReview.requirement_module_id==module_id, RequirementReview.status.in_(["pending_review","approved"])).values(status="superseded"))
    # 新流程没有评审中间层；模块变更后必须使其直接生成的已确认用例失效。
    await db.execute(update(RequirementTestCase).where(
        RequirementTestCase.project_id == project_id,
        RequirementTestCase.requirement_module_id == module_id,
        RequirementTestCase.review_id.is_(None),
        RequirementTestCase.status == "confirmed",
    ).values(status="needs_review", revision=RequirementTestCase.revision + 1))
    scenarios=(await db.scalars(select(TestScenario).where(TestScenario.project_id==project_id))).all()
    for scenario in scenarios:
        if hasattr(scenario, "requirement_module_ids") and module_id in (scenario.requirement_module_ids or []): scenario.status="needs_review"; scenario.revision+=1

async def update_module(db,project_id,user,module_id,data,confirm=False,expected_revision=None):
    await require_membership(db,project_id,user); row=await db.scalar(select(RequirementModule).where(RequirementModule.id==module_id,RequirementModule.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","需求模块不存在",404)
    if expected_revision is not None and row.revision != expected_revision: raise AppError("REVISION_CONFLICT","需求模块已被修改",409,{"current_revision":row.revision})
    if data and row.revision!=data.revision: raise AppError("REVISION_CONFLICT","需求模块已被修改",409,{"current_revision":row.revision})
    if data:
        was_confirmed=row.status in {"confirmed","changed"}
        source_type=getattr(data, "source_type", getattr(row, "source_type", "content_blocks"))
        await _validate_module_source(db, project_id, row.document_version_id, data.source_block_ids, source_type)
        row.name=data.name; row.description=data.description; row.source_block_ids=data.source_block_ids; row.source_type=source_type; row.updated_by=user.id; row.revision+=1
        if was_confirmed:
            row.status="changed"; row.confirmed_by=None; row.confirmed_at=None
            await _mark_module_dependents_for_review(db, project_id, row.id)
    if confirm:
        await _validate_module_source(db, project_id, row.document_version_id, row.source_block_ids, row.source_type)
        if row.status in {"archived", "needs_review"}: raise AppError("MODULE_CONFIRM_CONFLICT", "归档或待复核模块不能直接确认", 409)
        row.status="confirmed"; row.confirmed_by=user.id; row.confirmed_at=datetime.now(UTC); row.updated_by=user.id; row.revision+=1
    await db.commit(); await db.refresh(row); return row

async def split_document_modules(db, project_id, user, document_id, data):
    # 自动拆分只产生 pending_confirmation 候选，不直接创建可使用的正式模块。
    await require_membership(db, project_id, user)
    document=await db.scalar(select(RequirementDocument).where(RequirementDocument.id == document_id, RequirementDocument.project_id == project_id))
    if not document: raise AppError("RESOURCE_NOT_FOUND", "需求文档不存在", 404)
    version=await db.scalar(select(DocumentVersion).where(DocumentVersion.id == data.document_version_id, DocumentVersion.document_id == document.id, DocumentVersion.project_id == project_id))
    if not version or version.parse_status != "completed": raise AppError("DOCUMENT_NOT_PARSED", "文档尚未解析完成", 409)
    if version.content_status != "confirmed": raise AppError("DOCUMENT_CONTENT_NOT_CONFIRMED", "请先确认原始需求全文并等待解析完成", 409)
    if data.method == "ai":
        active=await db.scalar(select(RequirementModuleSplitJob).where(RequirementModuleSplitJob.document_version_id == version.id, RequirementModuleSplitJob.status.in_(["pending", "running"])))
        if active: raise AppError("MODULE_SPLIT_IN_PROGRESS", "当前文档版本已有拆分任务正在执行", 409, {"job_id": active.id})
        job=RequirementModuleSplitJob(project_id=project_id, document_version_id=version.id, method="ai", status="pending", created_by=user.id)
        db.add(job); await db.commit(); await db.refresh(job)
        try: enqueue_unique("app.worker_jobs.split_requirement_modules_job", job.id, 180)
        except AppError:
            job.status, job.error_code, job.error_message = "failed", "QUEUE_UNAVAILABLE", "AI 拆分任务队列不可用"
            await db.commit(); raise
        return {"job": split_job_view(job)}
    return await _persist_split_candidates(db, project_id, user, document, version, data.method)

async def _persist_split_candidates(db, project_id, user, document, version, method, ai_candidates=None, fallback_used=False, split_job=None):
    # 保存拆分候选前先清理同一版本旧的待确认候选，避免重复点击产生重复模块。
    blocks=(await db.scalars(select(ContentBlock).where(ContentBlock.document_version_id == version.id).order_by(ContentBlock.seq))).all()
    raw=[block_view(block) for block in blocks]
    candidates=ai_candidates or suggest_modules(raw)
    if method == "heading":
        candidates=[candidate for candidate in candidates if candidate.get("split_method") == "heading"]
    existing_statement = select(RequirementModule).where(
        RequirementModule.document_version_id == version.id,
        RequirementModule.status == "pending_confirmation",
        RequirementModule.split_method.in_(["heading", "rule", "ai", "rule_fallback"]),
    )
    existing = (await db.scalars(existing_statement)).all()
    for item in existing: await db.delete(item)
    ids_by_seq={block.seq:block.id for block in blocks}
    for index, candidate in enumerate(candidates, 1):
        db.add(RequirementModule(project_id=project_id, document_version_id=version.id, name=candidate["name"], description=candidate["description"], source_block_ids=[ids_by_seq[seq] for seq in candidate["source_seqs"] if seq in ids_by_seq], source_type="content_blocks", split_method=candidate.get("split_method", method), confidence=candidate.get("confidence"), sort_order=index, created_by=user.id, updated_by=user.id, status="pending_confirmation"))
    if split_job: split_job.status, split_job.fallback_used = "completed", fallback_used
    await db.commit()
    return await get_document(db, project_id, user, document.id, version.id)

async def split_module(db, project_id, user, module_id, data):
    await require_membership(db, project_id, user)
    row=await db.scalar(select(RequirementModule).where(RequirementModule.id == module_id, RequirementModule.project_id == project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND", "需求模块不存在", 404)
    if row.revision != data.revision: raise AppError("REVISION_CONFLICT", "需求模块已被修改", 409, {"current_revision": row.revision})
    if row.status == "archived": raise AppError("MODULE_SPLIT_CONFLICT", "归档模块不能拆分", 409)
    for item in data.modules:
        if item.document_version_id != row.document_version_id: raise AppError("INVALID_DOCUMENT_VERSION", "拆分模块必须属于原文档版本", 422)
        await _validate_module_source(db, project_id, row.document_version_id, item.source_block_ids, item.source_type)
        if not set(item.source_block_ids) <= set(row.source_block_ids): raise AppError("INVALID_SOURCE_BLOCK", "拆分来源必须来自原模块", 422)
    if set(data.modules[0].source_block_ids).intersection(data.modules[1].source_block_ids):
        raise AppError("MODULE_SPLIT_SOURCE_OVERLAP", "拆分后的模块不能重复引用同一来源内容块", 422)
    referenced=await _module_is_referenced(db, project_id, row.id)
    if referenced or row.status == "confirmed":
        row.status, row.archived_at, row.revision, row.updated_by = "archived", datetime.now(UTC), row.revision + 1, user.id
        await _mark_module_dependents_for_review(db, project_id, row.id)
    else: await db.delete(row)
    for index, item in enumerate(data.modules):
        db.add(RequirementModule(project_id=project_id, document_version_id=row.document_version_id, parent_module_id=row.id if referenced else None, name=item.name, description=item.description, source_block_ids=item.source_block_ids, source_type=item.source_type, split_method="manual", sort_order=row.sort_order + index, created_by=user.id, updated_by=user.id))
    await db.commit()

async def merge_modules(db, project_id, user, data):
    await require_membership(db, project_id, user)
    rows=(await db.scalars(select(RequirementModule).where(RequirementModule.project_id == project_id, RequirementModule.id.in_(data.module_ids)))).all()
    if len(rows) != len(set(data.module_ids)): raise AppError("RESOURCE_NOT_FOUND", "需求模块不存在", 404)
    version_ids={row.document_version_id for row in rows}
    if len(version_ids) != 1: raise AppError("INVALID_DOCUMENT_VERSION", "只能合并同一文档版本的模块", 422)
    for row in rows:
        if data.revision_by_id.get(row.id) != row.revision: raise AppError("REVISION_CONFLICT", "需求模块已被修改", 409, {"current_revision": row.revision})
    source_ids=list(dict.fromkeys(block_id for row in rows for block_id in row.source_block_ids))
    source_type="content_blocks" if source_ids else "manual"
    merged=RequirementModule(project_id=project_id, document_version_id=rows[0].document_version_id, name=data.name, description=data.description, source_block_ids=source_ids, source_type=source_type, split_method="manual", sort_order=min(row.sort_order for row in rows), created_by=user.id, updated_by=user.id)
    db.add(merged)
    for row in rows:
        if await _module_is_referenced(db, project_id, row.id) or row.status == "confirmed":
            row.status, row.archived_at, row.revision, row.updated_by = "archived", datetime.now(UTC), row.revision + 1, user.id
            await _mark_module_dependents_for_review(db, project_id, row.id)
        else: await db.delete(row)
    await db.commit(); await db.refresh(merged); return merged

async def reorder_modules(db, project_id, user, data):
    await require_membership(db, project_id, user)
    rows=(await db.scalars(select(RequirementModule).where(RequirementModule.project_id == project_id, RequirementModule.id.in_(data.module_ids)))).all()
    if len(rows) != len(set(data.module_ids)): raise AppError("RESOURCE_NOT_FOUND", "需求模块不存在", 404)
    if len({row.document_version_id for row in rows}) != 1: raise AppError("INVALID_DOCUMENT_VERSION", "只能排序同一文档版本模块", 422)
    by_id={row.id: row for row in rows}
    for module_id, revision in data.revisions.items():
        if module_id in by_id and by_id[module_id].revision != revision: raise AppError("REVISION_CONFLICT", "需求模块已被修改", 409, {"current_revision": by_id[module_id].revision})
    for order, module_id in enumerate(data.module_ids, 1): by_id[module_id].sort_order, by_id[module_id].updated_by = order, user.id
    await db.commit()

async def confirm_modules(db, project_id, user, document_id, document_version_id, revision_by_id):
    await require_membership(db, project_id, user)
    version=await db.scalar(select(DocumentVersion).where(DocumentVersion.id == document_version_id, DocumentVersion.document_id == document_id, DocumentVersion.project_id == project_id))
    if not version: raise AppError("RESOURCE_NOT_FOUND", "需求文档不存在", 404)
    statement = select(RequirementModule).where(
        RequirementModule.document_version_id == version.id,
        RequirementModule.status.in_(["pending_confirmation", "changed"]),
    )
    rows = (await db.scalars(statement)).all()
    for row in rows:
        if revision_by_id.get(row.id) != row.revision: raise AppError("REVISION_CONFLICT", "需求模块已被修改", 409, {"module_id": row.id, "current_revision": row.revision})
        await _validate_module_source(db, project_id, row.document_version_id, row.source_block_ids, row.source_type)
        row.status, row.confirmed_by, row.confirmed_at, row.updated_by, row.revision = "confirmed", user.id, datetime.now(UTC), user.id, row.revision + 1
    await db.commit()
