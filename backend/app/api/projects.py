from fastapi import APIRouter, Request

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.schemas.identity import EnvironmentCreate, EnvironmentUpdate, MemberCreate, ProjectCreate
from app.services import identity

router = APIRouter(prefix="/projects", tags=["projects"])


def project_view(project, role: str | None = None) -> dict:
    data = {"id": project.id, "name": project.name, "description": project.description, "owner_id": project.owner_id, "status": project.status, "revision": project.revision, "created_at": project.created_at.isoformat()}
    if role:
        data["role"] = role
    return data


def env_view(row) -> dict:
    return {"id": row.id, "project_id": row.project_id, "name": row.name, "base_url": row.base_url, "variables": row.variables, "global_headers": row.global_headers, "secret_refs": row.secret_refs, "is_enabled": row.is_enabled, "revision": row.revision}


@router.get("")
async def projects(request: Request, db: DbSession, user: CurrentUser):
    rows = await identity.list_projects(db, user)
    return success([project_view(project, role) for project, role in rows], request.state.trace_id)


@router.post("", status_code=201)
async def create_project(data: ProjectCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(project_view(await identity.create_project(db, user, data), "Owner"), request.state.trace_id)


@router.get("/{project_id}/members")
async def members(project_id: str, request: Request, db: DbSession, user: CurrentUser):
    rows = await identity.list_members(db, project_id, user)
    return success([{"id": member.id, "user_id": member.user_id, "username": account.username, "name": account.name, "role": member.role} for member, account in rows], request.state.trace_id)


@router.post("/{project_id}/members", status_code=201)
async def add_member(project_id: str, data: MemberCreate, request: Request, db: DbSession, user: CurrentUser):
    member = await identity.add_member(db, project_id, user, data)
    return success({"id": member.id, "user_id": member.user_id, "role": member.role}, request.state.trace_id)


@router.get("/{project_id}/environments")
async def environments(project_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success([env_view(row) for row in await identity.list_environments(db, project_id, user)], request.state.trace_id)


@router.post("/{project_id}/environments", status_code=201)
async def create_environment(project_id: str, data: EnvironmentCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(env_view(await identity.create_environment(db, project_id, user, data)), request.state.trace_id)


@router.patch("/{project_id}/environments/{env_id}")
async def update_environment(project_id: str, env_id: str, data: EnvironmentUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(env_view(await identity.update_environment(db, project_id, env_id, user, data)), request.state.trace_id)
