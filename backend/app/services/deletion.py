"""Explicit deletion workflows for resources whose database FKs are intentional.

These functions keep deletion policy in one place.  In particular, audit users
are deactivated rather than physically removed and running jobs are protected.
"""
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings

from app.errors import AppError
from app.models import (
    ApiImport, ApiInterface, ApiModule, ApiScenarioCandidate, ContentBlock,
    DebugRun, DocumentImage, DocumentParseJob, DocumentVersion, ExecutionStep,
    ExecutionTask, LlmCallRecord, ModelConfig, ModelConfigRevision, Project,
    ProjectMember, ReportStep, RequirementCoverage, RequirementDataItem,
    RequirementDocument, RequirementModule, RequirementModuleSplitJob,
    RequirementReview, RequirementTestCase, RequirementTestPoint, ScenarioStep,
    TestEnvironment, TestReport, TestScenario, UiAutomationCandidate,
    UiCollectedElement, UiCollectedPage, UiCollectionSession,
    UiCollectionSnapshot, UiElement, UiEvidence, UiExecutionReport,
    UiExecutionReportStep, UiExecutionStep, UiExecutionTask,
    UiExplorationSession, UiExplorationStep, UiExplorationTurn, UiLocatorCandidate,
    UiLocatorRevision, UiModule, UiPage, UiPageStep, UiPageStepDetail,
    UiScenario, UiScenarioStep, User, LocatorVerification,
)
from app.services.identity import require_membership, require_system_admin


ADMIN_ROLES = {"Owner", "Admin"}
RUNNING = {"pending", "running", "queued", "starting"}


async def _member(db: AsyncSession, project_id: str, actor: User):
    return await require_membership(db, project_id, actor, ADMIN_ROLES)


async def _one(db, model, ident, *, project_id=None, code="RESOURCE_NOT_FOUND", label="资源"):
    query = select(model).where(model.id == ident)
    if project_id is not None and hasattr(model, "project_id"):
        query = query.where(model.project_id == project_id)
    row = await db.scalar(query)
    if row is None:
        raise AppError(code, f"{label}不存在", 404)
    return row


async def _delete(db, row):
    await db.delete(row)
    await db.commit()


async def delete_project_member(db, project_id, member_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, ProjectMember, member_id, code="MEMBER_NOT_FOUND", label="项目成员")
    if row.project_id != project_id:
        raise AppError("MEMBER_NOT_FOUND", "项目成员不存在", 404)
    if row.role == "Owner":
        count = await db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id, ProjectMember.role == "Owner", ProjectMember.id != row.id).limit(1))
        if count is None:
            raise AppError("LAST_OWNER_PROTECTED", "不能删除项目最后一个所有者", 422)
    await _delete(db, row)


async def delete_environment(db, project_id, env_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, TestEnvironment, env_id, project_id=project_id, label="测试环境")
    refs = await db.scalar(select(ExecutionTask.id).where(ExecutionTask.environment_id == env_id).limit(1))
    ui_refs = await db.scalar(select(UiExecutionTask.id).where(UiExecutionTask.environment_id == env_id).limit(1))
    exploration_refs = await db.scalar(select(UiExplorationSession.id).where(UiExplorationSession.environment_id == env_id).limit(1))
    if refs or ui_refs or exploration_refs:
        raise AppError("RESOURCE_IN_USE", "测试环境仍被执行任务或探索记录引用，请先删除相关记录", 409)
    await _delete(db, row)


async def delete_user(db, actor, user_id):
    require_system_admin(actor)
    target = await _one(db, User, user_id, code="USER_NOT_FOUND", label="用户")
    if target.id == actor.id:
        raise AppError("CANNOT_DISABLE_SELF", "不允许删除当前登录用户", 422)
    if target.system_role == "admin" and target.is_active:
        count = await db.scalar(select(User.id).where(User.system_role == "admin", User.is_active.is_(True), User.id != target.id).limit(1))
        if count is None:
            raise AppError("LAST_ADMIN_PROTECTED", "不允许删除最后一个活跃管理员", 422)
    target.is_active = False
    await db.commit()
    return target


async def delete_document_version(db, project_id, document_id, version_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, DocumentVersion, version_id, project_id=project_id, label="需求文档版本")
    if row.document_id != document_id:
        raise AppError("RESOURCE_NOT_FOUND", "需求文档版本不存在", 404)
    module_ids = list((await db.scalars(select(RequirementModule.id).where(RequirementModule.document_version_id == version_id))).all())
    if module_ids:
        review_ids = select(RequirementReview.id).where(RequirementReview.requirement_module_id.in_(module_ids))
        await _delete_where(db, RequirementCoverage, RequirementCoverage.test_point_id.in_(select(RequirementTestPoint.id).where(RequirementTestPoint.review_id.in_(review_ids))))
        await _delete_where(db, RequirementTestPoint, RequirementTestPoint.review_id.in_(review_ids))
        await _delete_where(db, RequirementReview, RequirementReview.requirement_module_id.in_(module_ids))
    await _delete_where(db, RequirementTestCase, RequirementTestCase.document_version_id == version_id)
    await _delete_where(db, RequirementDataItem, RequirementDataItem.document_version_id == version_id)
    await _delete_where(db, RequirementModule, RequirementModule.document_version_id == version_id)
    await _delete_where(db, ContentBlock, ContentBlock.document_version_id == version_id)
    images = list((await db.scalars(select(DocumentImage).where(DocumentImage.document_version_id == version_id))).all())
    for image in images:
        _remove_upload(image.object_key)
    _remove_upload(row.object_key)
    await _delete_where(db, DocumentImage, DocumentImage.document_version_id == version_id)
    await _delete_where(db, DocumentParseJob, DocumentParseJob.document_version_id == version_id)
    await _delete_where(db, RequirementModuleSplitJob, RequirementModuleSplitJob.document_version_id == version_id)
    await _delete(db, row)


async def _delete_where(db, model, condition):
    await db.execute(delete(model).where(condition))


def _remove_upload(object_key: str | None) -> None:
    if not object_key:
        return
    target = (get_settings().upload_root / object_key).resolve()
    root = get_settings().upload_root.resolve()
    if root == target or root not in target.parents:
        return
    target.unlink(missing_ok=True)


async def delete_document(db, project_id, document_id, actor):
    await _member(db, project_id, actor)
    doc = await _one(db, RequirementDocument, document_id, project_id=project_id, label="需求文档")
    versions = list((await db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id))).all())
    for version in versions:
        await delete_document_version(db, project_id, doc.id, version.id, actor)
    await _delete(db, doc)


async def delete_api_import(db, project_id, import_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, ApiImport, import_id, project_id=project_id, label="API导入记录")
    interfaces = list((await db.scalars(select(ApiInterface).where(ApiInterface.import_id == import_id))).all())
    for interface in interfaces:
        await _delete_api_interface(db, project_id, interface.id)
    await _delete(db, row)


async def _delete_api_interface(db, project_id, interface_id):
    await _delete_where(db, ScenarioStep, ScenarioStep.interface_id == interface_id)
    row = await _one(db, ApiInterface, interface_id, project_id=project_id, label="API接口")
    await db.delete(row)


async def delete_api_module(db, project_id, module_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, ApiModule, module_id, project_id=project_id, label="API模块")
    await db.execute(update(ApiInterface).where(ApiInterface.module_id == module_id).values(module_id=None))
    await _delete(db, row)


async def delete_api_scenario(db, project_id, scenario_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, TestScenario, scenario_id, project_id=project_id, label="API场景")
    await _delete_where(db, TestReport, TestReport.execution_id.in_(select(ExecutionTask.id).where(ExecutionTask.scenario_id == scenario_id)))
    await _delete_where(db, ExecutionTask, ExecutionTask.scenario_id == scenario_id)
    await _delete_where(db, ScenarioStep, ScenarioStep.scenario_id == scenario_id)
    await _delete(db, row)


async def delete_api_execution(db, project_id, execution_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, ExecutionTask, execution_id, project_id=project_id, label="接口执行任务")
    if row.status in RUNNING:
        raise AppError("EXECUTION_RUNNING", "运行中的执行任务不能删除，请先取消", 409)
    reports = list((await db.scalars(select(TestReport).where(TestReport.execution_id == execution_id))).all())
    for report in reports:
        await _delete_where(db, ReportStep, ReportStep.report_id == report.id)
        await db.delete(report)
    await _delete_where(db, ExecutionStep, ExecutionStep.execution_id == execution_id)
    await _delete(db, row)


async def delete_api_report(db, project_id, report_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, TestReport, report_id, project_id=project_id, label="接口执行报告")
    await _delete_where(db, ReportStep, ReportStep.report_id == report_id)
    await _delete(db, row)


async def delete_ui_exploration(db, project_id, exploration_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, UiExplorationSession, exploration_id, project_id=project_id, label="UI探索记录")
    if row.status in RUNNING:
        raise AppError("EXPLORATION_RUNNING", "运行中的探索记录不能删除，请先取消", 409)
    await _delete_where(db, UiExplorationTurn, UiExplorationTurn.exploration_id == exploration_id)
    await _delete_where(db, UiExplorationStep, UiExplorationStep.exploration_id == exploration_id)
    await _delete(db, row)


async def delete_ui_execution(db, project_id, execution_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, UiExecutionTask, execution_id, project_id=project_id, label="UI执行任务")
    if row.status in RUNNING:
        raise AppError("EXECUTION_RUNNING", "运行中的执行任务不能删除，请先取消", 409)
    await _delete_where(db, UiExecutionReport, UiExecutionReport.execution_id == execution_id)
    await _delete_where(db, UiExecutionStep, UiExecutionStep.execution_id == execution_id)
    await _delete(db, row)


async def delete_ui_report(db, project_id, report_id, actor):
    await _member(db, project_id, actor)
    row = await _one(db, UiExecutionReport, report_id, project_id=project_id, label="UI执行报告")
    await _delete(db, row)


async def delete_model_config(db, actor, config_id):
    require_system_admin(actor)
    row = await _one(db, ModelConfig, config_id, label="模型配置")
    if row.is_default:
        raise AppError("DEFAULT_MODEL_PROTECTED", "默认模型配置不能删除，请先切换默认配置", 422)
    refs = await db.scalar(select(ModelConfigRevision.id).where(ModelConfigRevision.model_config_id == config_id).limit(1))
    calls = await db.scalar(select(LlmCallRecord.id).where(LlmCallRecord.model_config_id == config_id).limit(1))
    review_refs = await db.scalar(select(RequirementReview.id).where(RequirementReview.model_config_id == config_id).limit(1))
    case_refs = await db.scalar(select(RequirementTestCase.id).where(RequirementTestCase.model_config_id == config_id).limit(1))
    candidate_refs = await db.scalar(select(ApiScenarioCandidate.id).where(ApiScenarioCandidate.model_config_id == config_id).limit(1))
    exploration_refs = await db.scalar(select(UiExplorationSession.id).where(UiExplorationSession.model_config_id == config_id).limit(1))
    if refs or calls or review_refs or case_refs or candidate_refs or exploration_refs:
        raise AppError("RESOURCE_IN_USE", "模型配置已有历史引用，不能物理删除", 409)
    await _delete(db, row)


async def delete_project(db, project_id, actor):
    await _member(db, project_id, actor)
    project = await _one(db, Project, project_id, label="项目")
    running = await db.scalar(select(ExecutionTask.id).where(ExecutionTask.project_id == project_id, ExecutionTask.status.in_(RUNNING)).limit(1))
    ui_running = await db.scalar(select(UiExecutionTask.id).where(UiExecutionTask.project_id == project_id, UiExecutionTask.status.in_(RUNNING)).limit(1))
    exploring = await db.scalar(select(UiExplorationSession.id).where(UiExplorationSession.project_id == project_id, UiExplorationSession.status.in_(RUNNING)).limit(1))
    if running or ui_running or exploring:
        raise AppError("PROJECT_RUNNING", "项目仍有运行中的任务或探索，不能删除", 409)
    # Null the two evidence back references before deleting project children.
    await db.execute(update(UiExecutionTask).where(UiExecutionTask.project_id == project_id).values(trace_manifest_ref=None))
    await db.execute(update(UiExecutionReport).where(UiExecutionReport.project_id == project_id).values(trace_manifest_ref=None))
    await db.execute(update(UiExplorationSession).where(UiExplorationSession.project_id == project_id).values(last_evidence_ref=None))
    # Project-owned rows are deleted from leaves to roots.  This also handles
    # RESTRICT FKs that make database-level project CASCADE insufficient.
    leaf_groups = [
        (UiExecutionReportStep, UiExecutionReportStep.project_id == project_id), (ReportStep, ReportStep.project_id == project_id),
        (UiExecutionReport, UiExecutionReport.project_id == project_id), (UiExecutionStep, UiExecutionStep.project_id == project_id), (UiExecutionTask, UiExecutionTask.project_id == project_id),
        (ExecutionStep, ExecutionStep.project_id == project_id), (TestReport, TestReport.project_id == project_id), (ExecutionTask, ExecutionTask.project_id == project_id),
        (UiScenarioStep, UiScenarioStep.project_id == project_id), (UiScenario, UiScenario.project_id == project_id), (ScenarioStep, ScenarioStep.project_id == project_id), (TestScenario, TestScenario.project_id == project_id),
        (UiExplorationTurn, UiExplorationTurn.project_id == project_id), (UiExplorationStep, UiExplorationStep.project_id == project_id), (UiExplorationSession, UiExplorationSession.project_id == project_id),
        (UiAutomationCandidate, UiAutomationCandidate.project_id == project_id), (UiEvidence, UiEvidence.project_id == project_id),
        (UiLocatorRevision, UiLocatorRevision.project_id == project_id), (UiLocatorCandidate, UiLocatorCandidate.project_id == project_id), (UiCollectedElement, UiCollectedElement.project_id == project_id), (UiCollectedPage, UiCollectedPage.project_id == project_id), (UiCollectionSnapshot, UiCollectionSnapshot.project_id == project_id), (UiCollectionSession, UiCollectionSession.project_id == project_id),
        (LocatorVerification, LocatorVerification.project_id == project_id), (UiPageStepDetail, UiPageStepDetail.project_id == project_id), (UiElement, UiElement.project_id == project_id), (UiPageStep, UiPageStep.project_id == project_id), (UiPage, UiPage.project_id == project_id), (UiModule, UiModule.project_id == project_id),
        (ApiScenarioCandidate, ApiScenarioCandidate.project_id == project_id), (DebugRun, DebugRun.project_id == project_id), (ApiInterface, ApiInterface.project_id == project_id), (ApiModule, ApiModule.project_id == project_id), (ApiImport, ApiImport.project_id == project_id),
        (RequirementCoverage, RequirementCoverage.project_id == project_id), (RequirementTestPoint, RequirementTestPoint.project_id == project_id), (RequirementTestCase, RequirementTestCase.project_id == project_id), (RequirementReview, RequirementReview.project_id == project_id), (RequirementModule, RequirementModule.project_id == project_id), (RequirementDataItem, RequirementDataItem.project_id == project_id), (RequirementModuleSplitJob, RequirementModuleSplitJob.project_id == project_id), (ContentBlock, ContentBlock.project_id == project_id), (DocumentImage, DocumentImage.project_id == project_id), (DocumentParseJob, DocumentParseJob.project_id == project_id), (DocumentVersion, DocumentVersion.project_id == project_id), (RequirementDocument, RequirementDocument.project_id == project_id),
        (LlmCallRecord, LlmCallRecord.project_id == project_id), (ModelConfigRevision, ModelConfigRevision.project_id == project_id), (TestEnvironment, TestEnvironment.project_id == project_id), (ProjectMember, ProjectMember.project_id == project_id),
    ]
    for model, condition in leaf_groups:
        await _delete_where(db, model, condition)
    await db.delete(project)
    await db.commit()
