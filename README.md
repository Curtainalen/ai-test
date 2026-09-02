# AI Test

AI 自动化测试平台一期 MVP，技术栈为 FastAPI、SQLAlchemy Async、PostgreSQL、Redis/RQ、React、TypeScript、Vite 和 Ant Design。

一期闭环：项目/环境 → 需求文档解析与模块确认 → OpenAPI 导入 → RequestComposer 调试 → 场景确认 → 异步执行 → WebSocket 进度 → 不可变脱敏报告。

## Docker 启动

```bash
copy .env.example .env
docker compose up --build
```

访问 `http://localhost:8080`；后端健康检查为 `http://localhost:8000/health`。

首次启动不创建默认账号。通过注册接口创建首个用户：

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"replace-with-strong-password","name":"管理员"}'
```

详细说明见 `docs/`。

## 测试账号

- 账号：`admin`
- 密码：`replace-with-strong-password`

## 本地前后端 + Docker 依赖启动

适用于本地调试：PostgreSQL 和 Redis 运行在 Docker 中，前端和后端运行在本机。

```powershell
# 1. 启动 Docker 依赖
docker compose up -d postgres redis

# 2. 启动本地后端（新终端）
cd backend
$env:DATABASE_URL='postgresql+asyncpg://ai_test:change-me@localhost:5432/ai_test'
$env:REDIS_URL='redis://localhost:6379/0'
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. 启动本地前端（新终端）
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 8080 --strictPort
```

访问 `http://localhost:8080` 登录；后端健康检查为 `http://localhost:8000/health`。
