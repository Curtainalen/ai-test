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


def test_editing_confirmed_requirement_marks_ai_coverage_for_review(monkeypatch):
    row = SimpleNamespace(id="module-1", project_id="project-1", document_version_id="version-1",
                          name="登录", description="旧描述", source_block_ids=["block-1"], status="confirmed",
                          revision=2, confirmed_by="user-1", confirmed_at=object())

    class UpdateDatabase:
        def __init__(self): self.statements = []
        async def scalar(self, _query): return row
        async def scalars(self, _query): return _Scalars(["block-1"])
        async def execute(self, statement): self.statements.append(statement)
        async def commit(self): pass
        async def refresh(self, _row): pass

    monkeypatch.setattr(requirement_assets, "require_membership", lambda *_: asyncio.sleep(0))
    db = UpdateDatabase()
    data = SimpleNamespace(revision=2, name="登录", description="新描述", source_block_ids=["block-1"])
    asyncio.run(requirement_assets.update_module(db, "project-1", SimpleNamespace(id="user-1"), "module-1", data))

    assert row.status == "changed" and row.revision == 3 and row.confirmed_by is None
    assert len(db.statements) == 2
    assert "requirement_coverages" in str(db.statements[0])
    assert "NEEDS_REVIEW" in db.statements[0].compile().params.values()
    assert "requirement_reviews" in str(db.statements[1])
