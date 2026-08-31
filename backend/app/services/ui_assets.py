from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import LocatorVerification, UiElement, UiModule, UiPage, UiPageStep, UiPageStepDetail, UiScenario, UiScenarioStep, User
from app.services.identity import require_membership


def _time(value):
    return value.isoformat() if value else None


def module_view(row: UiModule) -> dict:
    return {"id": row.id, "project_id": row.project_id, "parent_id": row.parent_id, "name": row.name, "description": row.description, "revision": row.revision, "created_by": row.created_by, "created_at": _time(row.created_at), "updated_at": _time(row.updated_at)}


def page_view(row: UiPage) -> dict:
    return {"id": row.id, "project_id": row.project_id, "module_id": row.module_id, "name": row.name, "url": row.url, "description": row.description, "revision": row.revision, "created_by": row.created_by, "created_at": _time(row.created_at), "updated_at": _time(row.updated_at)}


def element_view(row: UiElement) -> dict:
    return {"id": row.id, "project_id": row.project_id, "page_id": row.page_id, "name": row.name, "primary_locator": row.primary_locator, "fallback_locators": row.fallback_locators, "locator_index": row.locator_index, "iframe_locator": row.iframe_locator, "verified": row.verified, "verified_url": row.verified_url, "dom_fingerprint": row.dom_fingerprint, "last_verified_at": _time(row.last_verified_at), "revision": row.revision, "description": row.description, "created_by": row.created_by, "created_at": _time(row.created_at), "updated_at": _time(row.updated_at)}


def page_step_view(row: UiPageStep, details: Sequence[UiPageStepDetail] | None = None) -> dict:
    data = {"id": row.id, "project_id": row.project_id, "page_id": row.page_id, "module_id": row.module_id, "name": row.name, "description": row.description, "revision": row.revision, "created_by": row.created_by, "created_at": _time(row.created_at), "updated_at": _time(row.updated_at)}
    if details is not None:
        data["details"] = [page_step_detail_view(item) for item in details]
    return data


def page_step_detail_view(row: UiPageStepDetail) -> dict:
    return {"id": row.id, "project_id": row.project_id, "page_step_id": row.page_step_id, "step_sort": row.step_sort, "step_type": row.step_type, "element_id": row.element_id, "operation": row.operation, "input_value": row.input_value, "assertion": row.assertion, "description": row.description, "created_at": _time(row.created_at), "updated_at": _time(row.updated_at)}


def scenario_view(row: UiScenario, steps: Sequence[UiScenarioStep] | None = None) -> dict:
    data = {"id": row.id, "project_id": row.project_id, "module_id": row.module_id, "name": row.name, "description": row.description, "status": row.status, "revision": row.revision, "confirmed_at": _time(row.confirmed_at), "created_by": row.created_by, "created_at": _time(row.created_at), "updated_at": _time(row.updated_at)}
    if steps is not None:
        data["steps"] = [{"id": item.id, "page_step_id": item.page_step_id, "step_sort": item.step_sort, "data_override": item.data_override} for item in steps]
    return data


def verification_view(row: LocatorVerification, *, include_dom: bool = True) -> dict:
    data = {"id": row.id, "project_id": row.project_id, "page_id": row.page_id, "element_id": row.element_id, "element_revision": row.element_revision, "locator": row.locator, "iframe_locator": row.iframe_locator, "target_url": row.target_url, "actual_url": row.actual_url, "status": row.status, "match_count": row.match_count, "visible": row.visible, "actionable": row.actionable, "dom_fingerprint": row.dom_fingerprint, "evidence_ref": row.evidence_ref, "error_code": row.error_code, "error_message": row.error_message, "created_by": row.created_by, "created_at": _time(row.created_at)}
    if include_dom:
        data["dom_summary"] = row.dom_summary
    return data


async def _one(db: AsyncSession, model, project_id: str, row_id: str, label: str):
    row = await db.scalar(select(model).where(model.id == row_id, model.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", f"{label}不存在", 404)
    return row


async def _count(db: AsyncSession, model, *conditions) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


async def _paginate(db: AsyncSession, model, project_id: str, view, query) -> dict:
    stmt = select(model).where(model.project_id == project_id)
    if query.search:
        stmt = stmt.where(model.name.ilike(f"%{query.search.strip()}%"))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.scalars(stmt.order_by(model.updated_at.desc(), model.id.asc()).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
    return {"items": [view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def _commit(db: AsyncSession, duplicate_code: str, duplicate_message: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(duplicate_code, duplicate_message, 409) from exc


async def list_modules(db, project_id, user: User, query):
    await require_membership(db, project_id, user)
    return await _paginate(db, UiModule, project_id, module_view, query)


async def create_module(db, project_id, user: User, data):
    await require_membership(db, project_id, user)
    if data.parent_id:
        await _one(db, UiModule, project_id, data.parent_id, "父模块")
    row = UiModule(project_id=project_id, created_by=user.id, **data.model_dump())
    db.add(row)
    await _commit(db, "UI_MODULE_EXISTS", "同一项目内模块名称已存在")
    await db.refresh(row)
    return module_view(row)


async def get_module(db, project_id, user: User, module_id):
    await require_membership(db, project_id, user)
    return module_view(await _one(db, UiModule, project_id, module_id, "UI 模块"))


async def update_module(db, project_id, user: User, module_id, data):
    await require_membership(db, project_id, user)
    row = await _one(db, UiModule, project_id, module_id, "UI 模块")
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "UI 模块已被其他用户修改", 409, {"current_revision": row.revision})
    if data.parent_id:
        parent = await _one(db, UiModule, project_id, data.parent_id, "父模块")
        if parent.id == row.id:
            raise AppError("UI_MODULE_PARENT_INVALID", "模块不能将自身作为父模块", 422)
    for field in ("parent_id", "name", "description"):
        setattr(row, field, getattr(data, field))
    row.revision += 1
    await _commit(db, "UI_MODULE_EXISTS", "同一项目内模块名称已存在")
    await db.refresh(row)
    return module_view(row)


async def delete_module(db, project_id, user: User, module_id):
    await require_membership(db, project_id, user)
    row = await _one(db, UiModule, project_id, module_id, "UI 模块")
    if await _count(db, UiModule, UiModule.parent_id == row.id) or await _count(db, UiPage, UiPage.module_id == row.id) or await _count(db, UiScenario, UiScenario.module_id == row.id):
        raise AppError("UI_MODULE_REFERENCED", "模块仍被页面、场景或子模块引用，不能删除", 409)
    await db.delete(row)
    await db.commit()


async def list_pages(db, project_id, user: User, query, module_id: str | None = None):
    await require_membership(db, project_id, user)
    if module_id:
        await _one(db, UiModule, project_id, module_id, "UI 模块")
    stmt = select(UiPage).where(UiPage.project_id == project_id)
    if module_id:
        stmt = stmt.where(UiPage.module_id == module_id)
    if query.search:
        stmt = stmt.where(or_(UiPage.name.ilike(f"%{query.search.strip()}%"), UiPage.url.ilike(f"%{query.search.strip()}%")))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.scalars(stmt.order_by(UiPage.updated_at.desc(), UiPage.id.asc()).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
    return {"items": [page_view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def create_page(db, project_id, user: User, data):
    await require_membership(db, project_id, user)
    await _one(db, UiModule, project_id, data.module_id, "UI 模块")
    row = UiPage(project_id=project_id, created_by=user.id, **data.model_dump())
    db.add(row)
    await _commit(db, "UI_PAGE_EXISTS", "同一模块内页面名称已存在")
    await db.refresh(row)
    return page_view(row)


async def get_page(db, project_id, user: User, page_id):
    await require_membership(db, project_id, user)
    return page_view(await _one(db, UiPage, project_id, page_id, "UI 页面"))


async def update_page(db, project_id, user: User, page_id, data):
    await require_membership(db, project_id, user)
    row = await _one(db, UiPage, project_id, page_id, "UI 页面")
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "UI 页面已被其他用户修改", 409, {"current_revision": row.revision})
    await _one(db, UiModule, project_id, data.module_id, "UI 模块")
    for field in ("module_id", "name", "url", "description"):
        setattr(row, field, getattr(data, field))
    row.revision += 1
    await _commit(db, "UI_PAGE_EXISTS", "同一模块内页面名称已存在")
    await db.refresh(row)
    return page_view(row)


async def delete_page(db, project_id, user: User, page_id):
    await require_membership(db, project_id, user)
    row = await _one(db, UiPage, project_id, page_id, "UI 页面")
    if await _count(db, UiElement, UiElement.page_id == row.id) or await _count(db, UiPageStep, UiPageStep.page_id == row.id) or await _count(db, LocatorVerification, LocatorVerification.page_id == row.id):
        raise AppError("UI_PAGE_REFERENCED", "页面仍被元素、页面步骤或验证记录引用，不能删除", 409)
    await db.delete(row)
    await db.commit()


async def list_elements(db, project_id, user: User, query, page_id: str | None = None):
    await require_membership(db, project_id, user)
    if page_id:
        await _one(db, UiPage, project_id, page_id, "UI 页面")
    stmt = select(UiElement).where(UiElement.project_id == project_id)
    if page_id:
        stmt = stmt.where(UiElement.page_id == page_id)
    if query.search:
        stmt = stmt.where(UiElement.name.ilike(f"%{query.search.strip()}%"))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.scalars(stmt.order_by(UiElement.updated_at.desc(), UiElement.id.asc()).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
    return {"items": [element_view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def create_element(db, project_id, user: User, data):
    await require_membership(db, project_id, user)
    await _one(db, UiPage, project_id, data.page_id, "UI 页面")
    payload = data.model_dump()
    row = UiElement(project_id=project_id, created_by=user.id, **payload)
    db.add(row)
    await _commit(db, "UI_ELEMENT_EXISTS", "同一页面内元素名称已存在")
    await db.refresh(row)
    return element_view(row)


async def get_element(db, project_id, user: User, element_id):
    await require_membership(db, project_id, user)
    return element_view(await _one(db, UiElement, project_id, element_id, "UI 元素"))


async def update_element(db, project_id, user: User, element_id, data):
    await require_membership(db, project_id, user)
    row = await _one(db, UiElement, project_id, element_id, "UI 元素")
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "UI 元素已被其他用户修改", 409, {"current_revision": row.revision})
    await _one(db, UiPage, project_id, data.page_id, "UI 页面")
    payload = data.model_dump(exclude={"revision"})
    locator_changed = any(getattr(row, field) != payload[field] for field in ("primary_locator", "fallback_locators", "locator_index", "iframe_locator"))
    for field, value in payload.items():
        setattr(row, field, value)
    row.revision += 1
    if locator_changed:
        row.verified = False
        row.verified_url = None
        row.dom_fingerprint = None
        row.last_verified_at = None
    await _commit(db, "UI_ELEMENT_EXISTS", "同一页面内元素名称已存在")
    await db.refresh(row)
    return element_view(row)


async def delete_element(db, project_id, user: User, element_id):
    await require_membership(db, project_id, user)
    row = await _one(db, UiElement, project_id, element_id, "UI 元素")
    if await _count(db, UiPageStepDetail, UiPageStepDetail.element_id == row.id):
        raise AppError("UI_ELEMENT_REFERENCED", "元素仍被页面步骤引用，不能删除", 409)
    await db.delete(row)
    await db.commit()


async def list_page_steps(db, project_id, user: User, query, page_id: str | None = None):
    await require_membership(db, project_id, user)
    stmt = select(UiPageStep).where(UiPageStep.project_id == project_id)
    if page_id:
        await _one(db, UiPage, project_id, page_id, "UI 页面")
        stmt = stmt.where(UiPageStep.page_id == page_id)
    if query.search:
        stmt = stmt.where(UiPageStep.name.ilike(f"%{query.search.strip()}%"))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.scalars(stmt.order_by(UiPageStep.updated_at.desc()).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
    return {"items": [page_step_view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def _validate_page_step_refs(db, project_id, page_id, module_id):
    page = await _one(db, UiPage, project_id, page_id, "UI 页面")
    if page.module_id != module_id:
        raise AppError("UI_PAGE_STEP_SCOPE_INVALID", "页面步骤的模块必须与页面所属模块一致", 422)


async def create_page_step(db, project_id, user: User, data):
    await require_membership(db, project_id, user)
    await _validate_page_step_refs(db, project_id, data.page_id, data.module_id)
    row = UiPageStep(project_id=project_id, created_by=user.id, **data.model_dump())
    db.add(row)
    await _commit(db, "UI_PAGE_STEP_EXISTS", "同一页面内页面步骤名称已存在")
    await db.refresh(row)
    return page_step_view(row, [])


async def get_page_step(db, project_id, user: User, step_id):
    await require_membership(db, project_id, user)
    row = await _one(db, UiPageStep, project_id, step_id, "页面步骤")
    details = (await db.scalars(select(UiPageStepDetail).where(UiPageStepDetail.project_id == project_id, UiPageStepDetail.page_step_id == row.id).order_by(UiPageStepDetail.step_sort))).all()
    return page_step_view(row, details)


async def update_page_step(db, project_id, user: User, step_id, data):
    await require_membership(db, project_id, user)
    row = await _one(db, UiPageStep, project_id, step_id, "页面步骤")
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "页面步骤已被其他用户修改", 409, {"current_revision": row.revision})
    await _validate_page_step_refs(db, project_id, data.page_id, data.module_id)
    for field in ("page_id", "module_id", "name", "description"):
        setattr(row, field, getattr(data, field))
    row.revision += 1
    await _commit(db, "UI_PAGE_STEP_EXISTS", "同一页面内页面步骤名称已存在")
    return await get_page_step(db, project_id, user, row.id)


async def delete_page_step(db, project_id, user: User, step_id):
    await require_membership(db, project_id, user)
    row = await _one(db, UiPageStep, project_id, step_id, "页面步骤")
    if await _count(db, UiScenarioStep, UiScenarioStep.page_step_id == row.id):
        raise AppError("UI_PAGE_STEP_REFERENCED", "页面步骤仍被 UI 场景引用，不能删除", 409)
    await db.delete(row)
    await db.commit()


async def _validate_detail_element(db, project_id, step: UiPageStep, element_id: str | None):
    if not element_id:
        return
    element = await _one(db, UiElement, project_id, element_id, "UI 元素")
    if element.page_id != step.page_id:
        raise AppError("UI_STEP_ELEMENT_SCOPE_INVALID", "页面步骤只能引用同一页面的元素", 422)


async def create_page_step_detail(db, project_id, user: User, step_id, data):
    await require_membership(db, project_id, user)
    step = await _one(db, UiPageStep, project_id, step_id, "页面步骤")
    await _validate_detail_element(db, project_id, step, data.element_id)
    row = UiPageStepDetail(project_id=project_id, page_step_id=step.id, **data.model_dump())
    db.add(row)
    step.revision += 1
    await _commit(db, "UI_PAGE_STEP_DETAIL_EXISTS", "页面步骤详情序号已存在")
    await db.refresh(row)
    return page_step_detail_view(row)


async def update_page_step_detail(db, project_id, user: User, step_id, detail_id, data):
    await require_membership(db, project_id, user)
    step = await _one(db, UiPageStep, project_id, step_id, "页面步骤")
    row = await db.scalar(select(UiPageStepDetail).where(UiPageStepDetail.id == detail_id, UiPageStepDetail.project_id == project_id, UiPageStepDetail.page_step_id == step.id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "页面步骤详情不存在", 404)
    await _validate_detail_element(db, project_id, step, data.element_id)
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    step.revision += 1
    await _commit(db, "UI_PAGE_STEP_DETAIL_EXISTS", "页面步骤详情序号已存在")
    await db.refresh(row)
    return page_step_detail_view(row)


async def delete_page_step_detail(db, project_id, user: User, step_id, detail_id):
    await require_membership(db, project_id, user)
    step = await _one(db, UiPageStep, project_id, step_id, "页面步骤")
    row = await db.scalar(select(UiPageStepDetail).where(UiPageStepDetail.id == detail_id, UiPageStepDetail.project_id == project_id, UiPageStepDetail.page_step_id == step.id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "页面步骤详情不存在", 404)
    await db.delete(row)
    step.revision += 1
    await db.commit()


async def _validate_scenario_steps(db, project_id, module_id, steps):
    if len({item.step_sort for item in steps}) != len(steps):
        raise AppError("UI_SCENARIO_STEP_SEQUENCE_DUPLICATE", "场景步骤序号不能重复", 422)
    ids = {item.page_step_id for item in steps}
    if not ids:
        return
    rows = (await db.scalars(select(UiPageStep).where(UiPageStep.project_id == project_id, UiPageStep.id.in_(ids)))).all()
    if len(rows) != len(ids) or any(row.module_id != module_id for row in rows):
        raise AppError("UI_SCENARIO_STEP_SCOPE_INVALID", "UI 场景只能引用当前项目、当前模块的页面步骤", 422)


async def list_scenarios(db, project_id, user: User, query, module_id: str | None = None):
    await require_membership(db, project_id, user)
    stmt = select(UiScenario).where(UiScenario.project_id == project_id)
    if module_id:
        await _one(db, UiModule, project_id, module_id, "UI 模块")
        stmt = stmt.where(UiScenario.module_id == module_id)
    if query.search:
        stmt = stmt.where(UiScenario.name.ilike(f"%{query.search.strip()}%"))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.scalars(stmt.order_by(UiScenario.updated_at.desc()).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
    return {"items": [scenario_view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def create_scenario(db, project_id, user: User, data):
    await require_membership(db, project_id, user)
    await _one(db, UiModule, project_id, data.module_id, "UI 模块")
    await _validate_scenario_steps(db, project_id, data.module_id, data.steps)
    row = UiScenario(project_id=project_id, created_by=user.id, **data.model_dump(exclude={"steps"}))
    db.add(row)
    await db.flush()
    for item in data.steps:
        db.add(UiScenarioStep(project_id=project_id, scenario_id=row.id, **item.model_dump()))
    await _commit(db, "UI_SCENARIO_EXISTS", "同一模块内 UI 场景名称已存在")
    return await get_scenario(db, project_id, user, row.id)


async def get_scenario(db, project_id, user: User, scenario_id):
    await require_membership(db, project_id, user)
    row = await _one(db, UiScenario, project_id, scenario_id, "UI 场景")
    steps = (await db.scalars(select(UiScenarioStep).where(UiScenarioStep.project_id == project_id, UiScenarioStep.scenario_id == row.id).order_by(UiScenarioStep.step_sort))).all()
    return scenario_view(row, steps)


async def update_scenario(db, project_id, user: User, scenario_id, data):
    await require_membership(db, project_id, user)
    row = await _one(db, UiScenario, project_id, scenario_id, "UI 场景")
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "UI 场景已被其他用户修改", 409, {"current_revision": row.revision})
    await _one(db, UiModule, project_id, data.module_id, "UI 模块")
    await _validate_scenario_steps(db, project_id, data.module_id, data.steps)
    for field in ("module_id", "name", "description", "status"):
        setattr(row, field, getattr(data, field))
    row.revision += 1
    await db.execute(delete(UiScenarioStep).where(UiScenarioStep.scenario_id == row.id, UiScenarioStep.project_id == project_id))
    for item in data.steps:
        db.add(UiScenarioStep(project_id=project_id, scenario_id=row.id, **item.model_dump()))
    await _commit(db, "UI_SCENARIO_EXISTS", "同一模块内 UI 场景名称已存在")
    return await get_scenario(db, project_id, user, row.id)


async def delete_scenario(db, project_id, user: User, scenario_id):
    await require_membership(db, project_id, user)
    row = await _one(db, UiScenario, project_id, scenario_id, "UI 场景")
    await db.delete(row)
    await db.commit()


async def confirm_scenario(db, project_id, user: User, scenario_id, revision: int):
    from datetime import UTC, datetime
    await require_membership(db, project_id, user)
    row = await _one(db, UiScenario, project_id, scenario_id, "UI 场景")
    if row.revision != revision:
        raise AppError("REVISION_CONFLICT", "UI 场景已被其他用户修改", 409, {"current_revision": row.revision})
    if row.status != "draft":
        raise AppError("UI_SCENARIO_NOT_CONFIRMABLE", "只有草稿 UI 场景可以确认", 409)
    page_step_ids = list((await db.scalars(select(UiScenarioStep.page_step_id).where(
        UiScenarioStep.project_id == project_id, UiScenarioStep.scenario_id == row.id))).all())
    element_ids = list((await db.scalars(select(UiPageStepDetail.element_id).where(
        UiPageStepDetail.project_id == project_id, UiPageStepDetail.page_step_id.in_(page_step_ids),
        UiPageStepDetail.element_id.is_not(None)))).all()) if page_step_ids else []
    if element_ids:
        verified = int(await db.scalar(select(func.count()).select_from(UiElement).where(
            UiElement.project_id == project_id, UiElement.id.in_(set(element_ids)), UiElement.verified.is_(True))) or 0)
        if verified != len(set(element_ids)):
            raise AppError("UI_SCENARIO_LOCATORS_NOT_VERIFIED", "场景包含尚未验证的 Locator", 409)
    row.status, row.confirmed_at, row.revision = "confirmed", datetime.now(UTC), row.revision + 1
    from app.models.requirement_ai import RequirementCoverage
    coverages = list((await db.scalars(select(RequirementCoverage).where(
        RequirementCoverage.project_id == project_id, RequirementCoverage.scenario_type == "ui",
        RequirementCoverage.scenario_id == row.id))).all())
    for coverage in coverages:
        coverage.status = "CONFIRMED"
        coverage.revision += 1
    await db.commit()
    return scenario_view(row)


async def list_verifications(db, project_id, user: User, query, element_id: str | None = None, page_id: str | None = None):
    await require_membership(db, project_id, user)
    stmt = select(LocatorVerification).where(LocatorVerification.project_id == project_id)
    if element_id:
        await _one(db, UiElement, project_id, element_id, "UI 元素")
        stmt = stmt.where(LocatorVerification.element_id == element_id)
    if page_id:
        await _one(db, UiPage, project_id, page_id, "UI 页面")
        stmt = stmt.where(LocatorVerification.page_id == page_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.scalars(stmt.order_by(LocatorVerification.created_at.desc(), LocatorVerification.id.desc()).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
    return {"items": [verification_view(row, include_dom=False) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def get_verification(db, project_id, user: User, verification_id):
    await require_membership(db, project_id, user)
    return verification_view(await _one(db, LocatorVerification, project_id, verification_id, "验证记录"))
