# 部署说明

1. 从 `.env.example` 创建 `.env`，设置随机 PostgreSQL 密码和至少 32 字符的 JWT Secret。
2. 运行 `docker compose up -d --build`。
3. `backend` 独占 Alembic 迁移；`worker` 设置 `RUN_MIGRATIONS=false`，避免并发迁移。
4. 检查 `docker compose ps`，backend/postgres/redis 应为 healthy。
5. 首次使用通过 `/api/auth/register` 创建唯一首个管理员，此后该接口关闭。

生产环境应在外层 TLS 网关后运行，限制 PostgreSQL/Redis 不对公网暴露，并对上传卷和数据库做备份。

## 远程 OpenAPI 导入

默认关闭。启用前设置 `REMOTE_OPENAPI_ENABLED=true`，并在 `REMOTE_OPENAPI_ALLOWED_HOSTS` 中配置逗号分隔的精确域名或 `*.example.com` 形式的子域名规则。平台会在初始请求和每次重定向前重新校验协议、白名单与解析 IP，并拒绝内网、回环、链路本地、保留地址和 HTTPS 降级跳转。

Basic、Bearer 和自定义 Header 凭据仅存在于单次请求内存中，不会保存到导入记录、日志或差异快照。URL 查询参数不会写入导入来源元数据，生产环境仍应优先使用请求 Header 鉴权。
