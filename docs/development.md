# 本地开发、测试与迁移

## 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

另开终端运行 Worker：`python -m app.worker`。

## 前端

```powershell
cd frontend
npm install
npm run dev
```

## 测试入口

- 后端：在 `backend` 目录运行 `python -m pytest -q`。
- 前端：在 `frontend` 目录运行 `npm run build`。
- 迁移：`alembic upgrade head`，回退演练使用独立测试库运行 `alembic downgrade base`。
- Compose：复制 `.env.example` 为 `.env` 后运行 `docker compose config --quiet` 与 `docker compose up --build`。

禁止从仓库根目录用宽泛 pytest 模式收集临时脚本。

## 本地调试启动

测试账号：`admin` / `replace-with-strong-password`。

先在 Docker 中启动 PostgreSQL 和 Redis：

```powershell
docker compose up -d postgres redis
```

后端本地启动时使用宿主机地址：

```powershell
cd backend
$env:DATABASE_URL='postgresql+asyncpg://ai_test:change-me@localhost:5432/ai_test'
$env:REDIS_URL='redis://localhost:6379/0'
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端另开终端启动在 `8080`：

```powershell
cd frontend
npm run dev -- --host 0.0.0.0 --port 8080 --strictPort
```
