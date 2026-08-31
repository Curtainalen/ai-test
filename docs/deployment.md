# 部署说明

1. 从 `.env.example` 创建 `.env`，设置随机 PostgreSQL 密码和至少 32 字符的 JWT Secret。
2. 运行 `docker compose up -d --build`。
3. `backend` 独占 Alembic 迁移；`worker` 设置 `RUN_MIGRATIONS=false`，避免并发迁移。
4. 检查 `docker compose ps`，backend/postgres/redis 应为 healthy。
5. 首次使用通过 `/api/auth/register` 创建唯一首个管理员，此后该接口关闭。

生产环境应在外层 TLS 网关后运行，限制 PostgreSQL/Redis 不对公网暴露，并对上传卷和数据库做备份。
