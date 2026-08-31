from __future__ import annotations
from datetime import UTC,datetime
from pathlib import Path
from sqlalchemy import func,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.errors import AppError
from app.models import ContentBlock,DocumentParseJob,DocumentVersion,RequirementDocument,RequirementModule,RequirementReview,RequirementTestPoint,RequirementCoverage,TestScenario,User
from app.services.documents import ALLOWED,sha256_bytes,suggest_modules,validate_filename
from app.services.identity import require_membership
from app.services.queue import enqueue_unique

def version_view(v,job=None): return {"id":v.id,"document_id":v.document_id,"version":v.version,"file_name":v.file_name,"mime_type":v.mime_type,"file_size":v.file_size,"sha256":v.sha256,"parse_status":v.parse_status,"parse_error":v.parse_error,"job":({"id":job.id,"status":job.status,"progress":job.progress,"error_code":job.error_code,"error_message":job.error_message} if job else None),"created_at":v.created_at.isoformat()}
def block_view(b): return {"id":b.id,"seq":b.seq,"block_type":b.block_type,"content":b.content,"structured_content":b.structured_content,"source_locator":b.source_locator,"confidence":b.confidence,"needs_correction":b.needs_correction}
def module_view(m): return {"id":m.id,"name":m.name,"description":m.description,"source_block_ids":m.source_block_ids,"status":m.status,"revision":m.revision,"document_version_id":m.document_version_id}

async def list_modules(db,project_id,user,status:str|None=None):
    await require_membership(db,project_id,user)
    query=select(RequirementModule).where(RequirementModule.project_id==project_id)
    if status:
        query=query.where(RequirementModule.status==status)
    rows=(await db.scalars(query.order_by(RequirementModule.created_at.desc()))).all()
    return [module_view(row) for row in rows]

async def create_upload(db:AsyncSession,project_id:str,user:User,filename:str,content_type:str,content:bytes,title:str|None=None,document_id:str|None=None):
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
    object_key=f"{project_id}/{document.id}/{next_version}-{digest[:12]}{ext}"; target=settings.upload_root/object_key; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content)
    version=DocumentVersion(project_id=project_id,document_id=document.id,version=next_version,file_name=safe,object_key=object_key,mime_type=expected,file_size=len(content),sha256=digest,uploaded_by=user.id)
    db.add(version); await db.flush(); job=DocumentParseJob(project_id=project_id,document_version_id=version.id); db.add(job)
    try: await db.commit()
    except IntegrityError as exc:
        await db.rollback(); target.unlink(missing_ok=True); raise AppError("FILE_DUPLICATE","相同文件已上传",409) from exc
    try:
        enqueue_unique("app.worker_jobs.parse_document_job",version.id,settings.document_parse_timeout_seconds+30)
    except AppError:
        version.parse_status="failed"; version.parse_error="任务队列不可用"; job.status="failed"; job.error_code="QUEUE_UNAVAILABLE"; job.error_message="任务队列暂不可用，请稍后重试"; await db.commit(); raise
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
    return document,version,job

async def get_document(db,project_id,user,document_id):
    await require_membership(db,project_id,user)
    doc=await db.scalar(select(RequirementDocument).where(RequirementDocument.id==document_id,RequirementDocument.project_id==project_id))
    if not doc: raise AppError("RESOURCE_NOT_FOUND","需求文档不存在",404)
    versions=(await db.scalars(select(DocumentVersion).where(DocumentVersion.document_id==doc.id).order_by(DocumentVersion.version.desc()))).all(); version=versions[0]
    job=await db.scalar(select(DocumentParseJob).where(DocumentParseJob.document_version_id==version.id))
    blocks=(await db.scalars(select(ContentBlock).where(ContentBlock.document_version_id==version.id).order_by(ContentBlock.seq))).all()
    modules=(await db.scalars(select(RequirementModule).where(RequirementModule.document_version_id==version.id).order_by(RequirementModule.created_at))).all()
    return {"id":doc.id,"title":doc.title,"versions":[version_view(v,job if v.id==version.id else None) for v in versions],"blocks":[block_view(b) for b in blocks],"modules":[module_view(m) for m in modules]}

async def update_module(db,project_id,user,module_id,data,confirm=False):
    await require_membership(db,project_id,user); row=await db.scalar(select(RequirementModule).where(RequirementModule.id==module_id,RequirementModule.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","需求模块不存在",404)
    if data and row.revision!=data.revision: raise AppError("REVISION_CONFLICT","需求模块已被修改",409,{"current_revision":row.revision})
    if data:
        was_confirmed=row.status in {"confirmed","changed"}
        valid=set((await db.scalars(select(ContentBlock.id).where(ContentBlock.project_id==project_id,ContentBlock.document_version_id==row.document_version_id))).all())
        if not set(data.source_block_ids)<=valid: raise AppError("INVALID_SOURCE_BLOCK","来源内容块不属于该文档版本",422)
        row.name=data.name; row.description=data.description; row.source_block_ids=data.source_block_ids; row.revision+=1
        if was_confirmed:
            row.status="changed"; row.confirmed_by=None; row.confirmed_at=None
            point_ids=select(RequirementTestPoint.id).join(RequirementReview,RequirementReview.id==RequirementTestPoint.review_id).where(
                RequirementTestPoint.project_id==project_id,RequirementReview.project_id==project_id,
                RequirementReview.requirement_module_id==row.id)
            await db.execute(update(RequirementCoverage).where(
                RequirementCoverage.project_id==project_id,RequirementCoverage.test_point_id.in_(point_ids)).values(
                status="NEEDS_REVIEW",revision=RequirementCoverage.revision+1))
            await db.execute(update(RequirementReview).where(
                RequirementReview.project_id==project_id,RequirementReview.requirement_module_id==row.id,
                RequirementReview.status.in_(["pending_review","approved"])).values(status="superseded"))
    if confirm:
        if not row.source_block_ids: raise AppError("MODULE_SOURCE_REQUIRED","确认前必须关联来源内容块",422)
        row.status="confirmed"; row.confirmed_by=user.id; row.confirmed_at=datetime.now(UTC); row.revision+=1
    await db.commit(); await db.refresh(row); return row
