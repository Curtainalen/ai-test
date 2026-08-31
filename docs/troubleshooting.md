# 故障排查

| 现象 | 检查 |
|---|---|
| `QUEUE_UNAVAILABLE` | Redis 健康、`REDIS_URL`、worker 是否运行 |
| 文档长时间 pending | worker 日志、RQ 队列、上传卷是否同时挂载到 backend/worker |
| `VARIABLE_MISSING` | `details.variables[].name/paths`，检查环境/接口/用例/步骤变量优先级 |
| `TARGET_URL_FORBIDDEN` | 请求绝对 URL 必须与环境 Base URL 同源 |
| WebSocket 4401/4403 | 连接后 5 秒内发送 auth 消息；检查 JWT 和项目成员关系 |
| 场景无法执行 | 场景必须为 confirmed，环境必须启用 |
| Docker API 不可用 | 启动 Docker Desktop/daemon；CLI 可安装但 daemon 可能未运行 |
