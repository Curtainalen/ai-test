# 一期 API 与 WebSocket 契约

## 统一响应

成功：`{"success": true, "data": ..., "trace_id": "..."}`。

失败：`{"success": false, "error": {"code": "...", "message": "...", "details": ...}, "trace_id": "..."}`。

## 主要 REST API

| 方法与路径 | 用途 |
|---|---|
| `POST /api/auth/register` | 无用户时创建首个账号，之后仅管理员可创建 |
| `POST /api/auth/login` / `GET /api/auth/me` | 登录与当前用户 |
| `GET/POST /api/projects` | 项目列表/创建 |
| `GET/POST /api/projects/{project_id}/members` | 成员查询/添加 |
| `GET/POST/PATCH /api/projects/{project_id}/environments` | 环境管理 |
| `POST /api/projects/{project_id}/requirements/upload` | 上传并创建异步解析任务 |
| `GET /api/projects/{project_id}/requirements/{id}` | 文档版本、内容块和模块 |
| `PATCH/POST /api/projects/{project_id}/requirement-modules/{id}` | 编辑/确认模块 |
| `POST /api/projects/{project_id}/api-imports` | 上传 OpenAPI 并生成差异预览 |
| `POST /api/projects/{project_id}/api-imports/{id}/confirm` | 确认差异入库 |
| `GET /api/projects/{project_id}/interfaces` | 接口模块树/列表 |
| `POST /api/projects/{project_id}/requests/preview` | 不落库组合请求 |
| `POST /api/projects/{project_id}/requests/run` | 单接口执行并保存调试历史 |
| `GET/POST/PATCH /api/projects/{project_id}/scenarios` | 场景 CRUD，PATCH 使用 revision |
| `POST /api/projects/{project_id}/scenarios/{id}/confirm` | 人工确认场景 |
| `POST /api/projects/{project_id}/executions` | 以 Idempotency-Key 创建异步任务 |
| `POST /api/projects/{project_id}/executions/{id}/cancel` | 协作式取消 |
| `GET /api/projects/{project_id}/executions/{id}` | 当前快照 |
| `GET /api/projects/{project_id}/reports` | 报告筛选 |
| `GET /api/projects/{project_id}/reports/{id}` | 不可变报告详情 |

## WebSocket

`/ws/projects/{project_id}/executions/{execution_id}`。连接建立后 5 秒内发送 `{"type":"auth","token":"<JWT>"}`，避免 JWT 出现在 URL 和访问日志。

首帧：`snapshot`，包含任务和全部步骤。状态变化发送 `execution_update` 或 `step_update`；客户端发 `ping`，服务端回 `pong`。服务端每个事件包含递增 `version`，客户端发现版本断层时重新连接取得完整快照。

## 结构化错误码

- `AUTH_INVALID_CREDENTIALS`、`AUTH_FORBIDDEN`
- `PROJECT_ACCESS_DENIED`、`RESOURCE_NOT_FOUND`
- `REVISION_CONFLICT`、`IDEMPOTENCY_CONFLICT`
- `FILE_UNSUPPORTED`、`FILE_TOO_LARGE`、`FILE_DUPLICATE`、`DOCUMENT_PARSE_FAILED`
- `OPENAPI_INVALID`、`REMOTE_URL_FORBIDDEN`
- `VARIABLE_MISSING`（HTTP 422，details 含变量名和字段路径）
- `SCENARIO_NOT_CONFIRMED`、`EXECUTION_NOT_CANCELABLE`
