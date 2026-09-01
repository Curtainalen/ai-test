# 一期 API 与 WebSocket 契约

## 统一响应

成功：`{"success": true, "data": ..., "trace_id": "..."}`。

失败：`{"success": false, "error": {"code": "...", "message": "...", "details": ...}, "trace_id": "..."}`。

## 主要 REST API

| 方法与路径 | 用途 |
|---|---|
| `POST /api/auth/register` | 无用户时创建首个账号，之后仅管理员可创建 |
| `POST /api/auth/login` / `GET /api/auth/me` | 登录与当前用户 |
| `GET /api/auth/users` / `PATCH /api/auth/users/{user_id}` | 仅管理员的用户列表与更新；用户不可删除 |
| `GET/POST /api/projects` | 项目列表/创建 |
| `GET/POST /api/projects/{project_id}/members` | 成员查询/添加 |
| `GET/POST/PATCH /api/projects/{project_id}/environments` | 环境管理 |
| `POST /api/projects/{project_id}/requirements/upload` | 上传并创建异步解析任务；可传 `document_id` 创建不可变新版本 |
| `GET /api/projects/{project_id}/requirements` | 分页文档工作台列表：标题、最新版本、解析状态、文件名、上传时间 |
| `GET /api/projects/{project_id}/requirements/{id}?version_id=` | 文档版本、解析/拆分状态和模块；省略 `version_id` 取最新版，跨文档版本返回 `INVALID_DOCUMENT_VERSION` |
| `GET /api/projects/{project_id}/requirements/{id}/blocks?version_id=` | 当前版本的可追溯正文块；用于模块来源查看、边界选择和低置信度校正 |
| `GET /api/projects/{project_id}/requirements/{id}/impact?version_id=` | 文档版本差异：新增、移除、内容变更和待复核模块 |
| `PATCH /api/projects/{project_id}/content-blocks/{id}` | 仅接受 `content`，保存后清除 `needs_correction`；若该块已被确认模块引用，则模块、评审、覆盖和关联场景进入待复核 |
| `POST/PATCH/DELETE /api/projects/{project_id}/requirement-modules/{id}` | 手工新增、编辑、删除模块；有下游引用的删除改为归档并触发复核 |
| `POST /api/projects/{project_id}/requirements/{id}/split` | `ai`、`heading` 或 `rule` 自动拆分；AI 为异步候选并会在失败时回退到规则拆分 |
| `POST /api/projects/{project_id}/requirement-modules/{id}/split` | 将模块拆为多个子模块；每个来源块只能分配给一个子模块 |
| `POST /api/projects/{project_id}/ai/requirement-reviews` | 对已确认模块发起异步可测性评审；输入严格限定为该模块来源正文 |
| `GET /api/projects/{project_id}/ai/requirement-reviews` / `GET .../{id}` | 评审列表/详情：进度、六维评分、问题清单、建议和测试点候选 |
| `POST /api/projects/{project_id}/ai/requirement-reviews/{id}/decision` / `cancel` | 审核候选，或取消生成中的评审；仅批准后的测试点可被 API/UI 下游选择 |
| `GET /api/projects/{project_id}/ai/requirement-coverages` | 可读的模块名、测试点标题、场景名和覆盖状态 |
| `POST /api/projects/{project_id}/api-imports` | 上传 OpenAPI 并生成差异预览 |
| `POST /api/projects/{project_id}/api-imports/url` | 从白名单 URL 拉取 OpenAPI 并生成差异预览；鉴权仅用于本次请求 |
| `POST /api/projects/{project_id}/api-imports/{id}/confirm` | 确认差异入库；查询参数 `revision` 必填，可选 JSON `{"selected_stable_keys":[...]}` 仅上传勾选的新增/修改接口；传选择列表时不会自动删除已有接口 |
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
- `CANNOT_DISABLE_SELF`、`LAST_ADMIN_PROTECTED`、`USER_NOT_FOUND`
- `PROJECT_ACCESS_DENIED`、`RESOURCE_NOT_FOUND`
- `REVISION_CONFLICT`、`IDEMPOTENCY_CONFLICT`
- `FILE_UNSUPPORTED`、`FILE_TOO_LARGE`、`FILE_DUPLICATE`、`DOCUMENT_PARSE_FAILED`
- `OPENAPI_INVALID`、`REMOTE_URL_FORBIDDEN`
- `VARIABLE_MISSING`（HTTP 422，details 含变量名和字段路径）
- `SCENARIO_NOT_CONFIRMED`、`EXECUTION_NOT_CANCELABLE`
