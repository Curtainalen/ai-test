import asyncio
from types import SimpleNamespace

from app.services import requirement_assets


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Database:
    def __init__(self, rows):
        self.rows = rows
        self.query = None

    async def scalars(self, query):
        self.query = query
        return _Scalars(self.rows)


def test_list_confirmed_requirement_modules_checks_scope_and_filters(monkeypatch):
    calls = []

    async def require_membership(db, project_id, user):
        calls.append((project_id, user.id))

    monkeypatch.setattr(requirement_assets, "require_membership", require_membership)
    row = SimpleNamespace(id="module-1", name="登录", description="用户登录", source_block_ids=["block-1"], status="confirmed", revision=1, document_version_id="version-1")
    db = _Database([row])
    result = asyncio.run(requirement_assets.list_modules(db, "project-1", SimpleNamespace(id="user-1"), "confirmed"))

    assert calls == [("project-1", "user-1")]
    assert result == [{"id": "module-1", "name": "登录", "description": "用户登录", "source_block_ids": ["block-1"], "status": "confirmed", "revision": 1, "document_version_id": "version-1"}]
    assert "requirement_modules.project_id" in str(db.query)
    assert "requirement_modules.status" in str(db.query)
