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
