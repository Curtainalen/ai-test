"""需求文档存储迁移命令。

运行 ``python -m app.maintenance`` 会把历史明文原始文件改为 Fernet 密文，
并把对应文档重新放回解析与人工确认流程。命令只处理 document_versions /
document_images 中 ``storage_encrypted = false`` 的记录，重复运行是安全的。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import DocumentImage, DocumentParseJob, DocumentVersion, RequirementDataItem, ContentBlock
from app.security import encrypt_bytes, is_encrypted_bytes
from app.errors import AppError
from app.services.queue import enqueue_unique


def _replace_with_encrypted_file(path: Path) -> bool:
    """原子替换旧明文文件；进程中断时保留旧文件或完整密文，避免半写入。"""
    if not path.is_file():
        return False
    content = path.read_bytes()
    if is_encrypted_bytes(content):
        return True
    temporary = path.with_name(f".{path.name}.encrypting-{os.getpid()}")
    try:
        temporary.write_bytes(encrypt_bytes(content))
        temporary.replace(path)
        return True
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


async def encrypt_legacy_requirement_files(batch_size: int = 100) -> dict[str, int]:
    """迁移一批历史文件并重置正文审核状态，返回可用于运维审计的非敏感统计。"""
    settings = get_settings()
    migrated_versions = migrated_images = missing_files = queue_failures = 0
    parse_version_ids: list[str] = []
    async with AsyncSessionLocal() as db:
        versions = list((await db.scalars(select(DocumentVersion).where(
            DocumentVersion.storage_encrypted.is_(False)).order_by(DocumentVersion.created_at).limit(batch_size))).all())
        for version in versions:
            target = settings.upload_root / version.object_key
            if not _replace_with_encrypted_file(target):
                missing_files += 1
                continue
            # 密文化后必须重新解析：历史 ContentBlock 可能仍然含有未经脱敏的正文。
            version.storage_encrypted = True
            version.parse_status, version.parse_error = "pending", None
            version.content_status, version.content_confirmed_at, version.content_confirmed_by = "pending_confirmation", None, None
            version.full_text = ""
            await db.execute(ContentBlock.__table__.delete().where(ContentBlock.document_version_id == version.id))
            await db.execute(RequirementDataItem.__table__.delete().where(RequirementDataItem.document_version_id == version.id))
            job = await db.scalar(select(DocumentParseJob).where(DocumentParseJob.document_version_id == version.id))
            if job is None:
                db.add(DocumentParseJob(project_id=version.project_id, document_version_id=version.id, status="pending"))
            else:
                job.status, job.progress, job.error_code, job.error_message = "pending", 0, None, None
                job.started_at, job.finished_at = None, None
            migrated_versions += 1
            parse_version_ids.append(version.id)
        images = list((await db.scalars(select(DocumentImage).where(
            DocumentImage.storage_encrypted.is_(False)).order_by(DocumentImage.created_at).limit(batch_size))).all())
        for image in images:
            target = settings.upload_root / image.object_key
            if not _replace_with_encrypted_file(target):
                missing_files += 1
                continue
            image.storage_encrypted = True
            migrated_images += 1
        await db.commit()
    # 数据已提交后再入队；队列暂不可用时保留 pending 状态，运维可重跑命令补投任务。
    for version_id in parse_version_ids:
        try:
            enqueue_unique("app.worker_jobs.parse_document_job", version_id, settings.document_parse_timeout_seconds + 30)
        except AppError:
            queue_failures += 1
    return {"migrated_versions": migrated_versions, "migrated_images": migrated_images, "missing_files": missing_files, "queue_failures": queue_failures}


if __name__ == "__main__":
    # 文件迁移和数据库提交完成后才投递解析任务，避免 Worker 读到未提交的中间状态。
    print(asyncio.run(encrypt_legacy_requirement_files()))
