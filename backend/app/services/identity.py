from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Project, ProjectMember, TestEnvironment, User
from app.schemas.identity import EnvironmentCreate, EnvironmentUpdate, MemberCreate, ProjectCreate, RegisterRequest, UserCreate
from app.security import hash_password, verify_password


async def register_first_user(db: AsyncSession, data: RegisterRequest) -> User:
    await db.execute(text("SELECT pg_advisory_xact_lock(209741925)"))
    count = await db.scalar(select(func.count(User.id)))
    if count:
        raise AppError("REGISTRATION_CLOSED", "首个账号已创建，请由管理员添加用户", 403)
    user = User(username=data.username, password_hash=hash_password(data.password), name=data.name, email=data.email, system_role="admin")
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("USERNAME_EXISTS", "用户名已存在", 409) from exc
    await db.refresh(user)
    return user


async def create_user(db: AsyncSession, actor: User, data: UserCreate) -> User:
    if actor.system_role != "admin":
        raise AppError("AUTH_FORBIDDEN", "仅系统管理员可创建用户", 403)
    user = User(username=data.username, password_hash=hash_password(data.password), name=data.name, email=data.email, system_role=data.system_role)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("USERNAME_EXISTS", "用户名已存在", 409) from exc
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", 401)
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return user


async def create_project(db: AsyncSession, user: User, data: ProjectCreate) -> Project:
    project = Project(name=data.name, description=data.description, owner_id=user.id)
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="Owner"))
    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(db: AsyncSession, user: User) -> list[tuple[Project, str]]:
    result = await db.execute(select(Project, ProjectMember.role).join(ProjectMember, ProjectMember.project_id == Project.id).where(ProjectMember.user_id == user.id).order_by(Project.created_at.desc()))
    return list(result.all())


async def require_membership(db: AsyncSession, project_id: str, user: User, roles: set[str] | None = None) -> tuple[Project, ProjectMember]:
    row = (await db.execute(select(Project, ProjectMember).join(ProjectMember, ProjectMember.project_id == Project.id).where(Project.id == project_id, ProjectMember.user_id == user.id))).one_or_none()
    if row is None:
        raise AppError("PROJECT_ACCESS_DENIED", "无权访问该项目", 403)
    project, membership = row
    if roles and membership.role not in roles:
        raise AppError("PROJECT_ACCESS_DENIED", "当前项目角色无权执行此操作", 403)
    return project, membership


async def add_member(db: AsyncSession, project_id: str, actor: User, data: MemberCreate) -> ProjectMember:
    await require_membership(db, project_id, actor, {"Owner", "Admin"})
    user = await db.scalar(select(User).where(User.username == data.username, User.is_active.is_(True)))
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 404)
    member = ProjectMember(project_id=project_id, user_id=user.id, role=data.role)
    db.add(member)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("MEMBER_EXISTS", "用户已是项目成员", 409) from exc
    await db.refresh(member)
    return member


async def list_members(db: AsyncSession, project_id: str, actor: User) -> list[tuple[ProjectMember, User]]:
    await require_membership(db, project_id, actor)
    result = await db.execute(select(ProjectMember, User).join(User, User.id == ProjectMember.user_id).where(ProjectMember.project_id == project_id).order_by(ProjectMember.created_at))
    return list(result.all())


async def list_environments(db: AsyncSession, project_id: str, actor: User) -> list[TestEnvironment]:
    await require_membership(db, project_id, actor)
    return list((await db.scalars(select(TestEnvironment).where(TestEnvironment.project_id == project_id).order_by(TestEnvironment.created_at))).all())


async def create_environment(db: AsyncSession, project_id: str, actor: User, data: EnvironmentCreate) -> TestEnvironment:
    await require_membership(db, project_id, actor)
    row = TestEnvironment(project_id=project_id, created_by=actor.id, **data.model_dump())
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("ENVIRONMENT_EXISTS", "环境名称已存在", 409) from exc
    await db.refresh(row)
    return row


async def update_environment(db: AsyncSession, project_id: str, env_id: str, actor: User, data: EnvironmentUpdate) -> TestEnvironment:
    await require_membership(db, project_id, actor)
    row = await db.scalar(select(TestEnvironment).where(TestEnvironment.id == env_id, TestEnvironment.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "环境不存在", 404)
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "环境已被其他用户修改", 409, {"current_revision": row.revision})
    for key, value in data.model_dump(exclude={"revision"}).items():
        setattr(row, key, value)
    row.revision += 1
    await db.commit()
    await db.refresh(row)
    return row
