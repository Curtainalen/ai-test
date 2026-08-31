# UI 自动化第一、二阶段开发提示词

请在当前仓库 `D:\Project\ai-test` 中实现 UI 自动化第一、二阶段功能。

## 一、角色与工程上下文

你现在是 12 年以上 Python 后端专家、前字节架构师，重视性能、可读性、边界安全和可测试性。

项目当前技术栈：

- 后端：Python 3.12、FastAPI、Uvicorn
- 数据访问：SQLAlchemy Async、Alembic、PostgreSQL
- 异步任务：Redis、RQ
- 前端：React、TypeScript、Vite、Ant Design
- 实时通信：FastAPI WebSocket
- 目录：`backend/app`、`frontend/src`

必须先阅读并遵守：

- `README.md`
- `docs/AI自动化测试.md`
- `docs/AI自动化测试-两三期开发计划.md`
- `docs/AI自动化测试-Skills与MCP清单.md`
- `docs/architecture.md`
- `docs/contracts.md`
- `docs/immutable-assets.md`
- `actuator/README.md`

必须先检查当前代码，复用已有的认证、项目、环境、错误响应、数据库、迁移、审计和测试模式。禁止假设这些能力不存在，也禁止另起一套架构。

## 二、任务目标

将 UI 自动化第一阶段和第二阶段合并实现为一个可交付任务：

```text
UI 领域模型与资产 API
  -> 手工录入页面、元素、页面步骤和场景
  -> 页面和定位器验证
  -> 保存验证证据
```

本任务不实现 AI，不实现 browser-use，不实现 Playwright MCP，不实现正式 actuator，不创建异步 UI 执行任务。

完成后，用户可以在不调用 LLM 的情况下：

1. 创建和管理 UI 模块。
2. 创建和管理 UI 页面。
3. 配置页面元素及主/备用定位器。
4. 通过受控 Playwright 验证页面和定位器。
5. 保存验证结果、DOM 摘要、页面 URL、匹配数量和截图引用。
6. 创建页面步骤及步骤详情。
7. 创建 UI 场景并组合页面步骤。
8. 查看和编辑上述资产。

## 三、产品边界

### 本次必须实现

- UI 模块、页面、元素、页面步骤、步骤详情、UI 场景的数据模型。
- 项目级数据隔离。
- 环境和目标域名校验。
- 页面、元素、步骤和场景 REST API。
- 页面可访问性验证。
- 定位器验证。
- 主定位器和备用定位器。
- CSS、XPath、ID、Role、Label、Placeholder、Name、Test ID 等定位方式。
- iframe 定位配置和验证。
- 验证结果和证据引用。
- 删除保护和引用完整性检查。
- 后端单元测试、API 测试和必要的前端测试。

### 本次禁止实现

- 任何 LLM 调用。
- AI 自动探索。
- AI 自动生成定位器。
- AI 自动生成测试场景。
- AI 自动修复定位器。
- 全站扫描。
- 正式 UI 回归执行。
- 独立 actuator 任务调度。
- 未经人工确认的自动资产写入。
- 引入新的第三方依赖。

## 四、核心业务约束

1. 所有 UI 资产必须绑定项目。
2. 页面必须绑定 UI 模块，元素必须绑定页面，页面步骤必须绑定页面和模块，场景必须绑定项目和模块。
3. 所有查询、创建、更新、删除和验证接口必须校验当前用户鉴权和项目权限。
4. 所有外部 HTTP 请求和 Playwright 操作必须带超时和取消上下文。
5. 禁止跨项目引用页面、元素、页面步骤、环境或证据文件。
6. 元素定位器验证匹配数量必须为 1，才允许标记为已验证。
7. 验证失败不得自动覆盖已有正式定位器。
8. 被页面步骤引用的元素不能删除。
9. 被场景引用的页面步骤不能删除。
10. 更新定位器必须产生新的 revision 或验证记录，不能破坏历史验证结果。
11. 证据文件只保存受控引用，不在数据库中保存不受限制的大型二进制内容。
12. 页面内容、DOM、截图和错误信息必须执行敏感信息脱敏。

## 五、推荐数据模型

请结合现有模型风格设计，不要机械照抄下列字段；如已有通用资产、项目、环境或文件模型，必须复用。

### UiModule

- `id`
- `project_id`
- `parent_id`（可选）
- `name`
- `description`
- `created_by`
- `created_at`
- `updated_at`

### UiPage

- `id`
- `project_id`
- `module_id`
- `name`
- `url`
- `description`
- `created_by`
- `created_at`
- `updated_at`

### UiElement

- `id`
- `project_id`
- `page_id`
- `name`
- `primary_locator_type`
- `primary_locator_value`
- `fallback_locators`（结构化 JSON）
- `locator_index`（可选）
- `is_iframe`
- `iframe_locator`（可选）
- `verified`
- `verified_url`
- `dom_fingerprint`
- `last_verified_at`
- `revision`
- `description`
- `created_by`
- `created_at`
- `updated_at`

### UiPageStep

- `id`
- `project_id`
- `page_id`
- `module_id`
- `name`
- `description`
- `revision`
- `created_by`
- `created_at`
- `updated_at`

### UiPageStepDetail

- `id`
- `page_step_id`
- `step_sort`
- `step_type`
- `element_id`（可选）
- `operation`
- `input_value`（必须支持敏感值引用，不保存明文密码）
- `assertion`（结构化 JSON）
- `description`
- `created_at`
- `updated_at`

### UiScenario

- `id`
- `project_id`
- `module_id`
- `name`
- `description`
- `status`
- `revision`
- `confirmed_at`（本任务只提供字段和状态，不实现 AI 确认流）
- `created_by`
- `created_at`
- `updated_at`

### UiScenarioStep

- `id`
- `scenario_id`
- `page_step_id`
- `step_sort`
- `data_override`（结构化 JSON）

### LocatorVerification

- `id`
- `project_id`
- `page_id`
- `element_id`（可选）
- `locator_type`
- `locator_value`
- `target_url`
- `status`
- `match_count`
- `visible`
- `actionable`
- `dom_fingerprint`
- `evidence_file_id`（可选）
- `error_code`（可选）
- `error_message`（脱敏）
- `created_by`
- `created_at`

## 六、定位器验证规则

定位器优先级：

```text
test_id / data-testid / 稳定 id
  -> role + name
  -> label / name / placeholder
  -> 稳定 CSS
  -> XPath
```

验证服务必须：

1. 校验目标 URL 是否匹配项目环境允许的域名。
2. 设置连接、导航、操作和总超时。
3. 使用独立 Browser Context。
4. 支持页面定位和 iframe 定位。
5. 返回匹配数量、可见性和可操作性。
6. 记录实际 URL 和 DOM 指纹。
7. 只允许匹配数量为 1 的结果成为 `verified=true`。
8. 对密码、Token、Cookie、Authorization 和个人信息进行脱敏。
9. 页面或定位器验证失败时保存结构化失败结果。
10. 禁止通过截图坐标代替定位器。

验证接口推荐：

```text
POST /api/projects/{project_id}/ui/pages/{page_id}/verify-access
POST /api/projects/{project_id}/ui/pages/{page_id}/verify-locator
POST /api/projects/{project_id}/ui/elements/{element_id}/verify
GET  /api/projects/{project_id}/ui/verifications
GET  /api/projects/{project_id}/ui/verifications/{verification_id}
```

## 七、严格执行顺序

请严格按照以下顺序输出和执行，不要打乱、不要省略任何步骤：

### 1. 现状检查和设计说明

先列出实际检查过的现有文件、模块和可复用能力。

然后用中文完整说明：

- 领域模型设计
- 聚合边界和引用关系
- revision 设计
- 项目和环境隔离
- 定位器数据结构
- 验证流程
- 超时和并发控制
- 证据文件处理
- 敏感数据脱敏
- 错误处理
- 与现有 Clean Architecture 或项目分层的对应关系

不得虚构当前仓库不存在的模块。

### 2. 文件路径清单

列出本次新增和修改的全部文件路径，并说明每个文件的职责。

优先遵循当前目录结构，例如：

```text
backend/app/models/
backend/app/schemas/
backend/app/api/
backend/app/services/
backend/app/migrations/versions/
backend/tests/
frontend/src/pages/
frontend/src/components/
frontend/src/api.ts
```

### 3. 数据模型、迁移和 Schema

实现 SQLAlchemy 模型、Alembic migration、Pydantic 请求/响应 Schema。

要求：

- 外键和唯一约束完整。
- 项目范围查询有明确过滤条件。
- 删除行为符合引用保护要求。
- JSON 字段有结构校验。
- 列表接口不得默认返回大字段。
- 分页、搜索和排序遵循项目已有模式。

### 4. 资产 API 和 application service

实现模块、页面、元素、页面步骤、步骤详情、场景和场景步骤 API。

要求：

- 所有接口校验登录用户。
- 所有资源校验项目权限。
- 禁止通过请求体中的 project_id 越权切换项目。
- 跨项目关联必须拒绝。
- 错误使用项目现有错误响应和异常处理机制。
- 不在 API 层堆积业务规则，业务逻辑放入 service。

### 5. Playwright 验证服务

实现页面访问和定位器验证服务，但不要接入 RQ 和正式 actuator。

要求：

- 验证任务必须有独立浏览器上下文。
- 所有导航、定位和操作都设置超时。
- 所有资源在 finally 中关闭。
- 不得使用全局浏览器实例。
- 不得把任意用户输入直接当作无限制脚本执行。
- 限制目标 URL、重定向和网络访问范围。
- 验证结果写入 `LocatorVerification` 或等价模型。

### 6. 前端资产管理页面

实现与现有前端风格一致的 UI：

- UI 模块列表和编辑。
- 页面列表和编辑。
- 页面元素列表和编辑。
- 定位器主备配置。
- 手工验证按钮和验证结果展示。
- 页面步骤编辑。
- UI 场景编辑。
- 验证历史查看。

前端必须处理加载、空数据、校验失败、权限错误、验证中、验证成功和验证失败状态。

### 7. 测试

至少补充以下测试：

1. 项目隔离：用户不能读取或修改其他项目的 UI 资产。
2. 引用保护：被步骤引用的元素和被场景引用的页面步骤不能删除。
3. 跨项目引用：创建步骤或场景时引用其他项目资源必须失败。
4. 定位器验证成功：唯一、可见、可操作的元素被标记为已验证。
5. 定位器验证失败：匹配数量为 0 或大于 1 时不能标记为已验证。
6. iframe 定位验证成功和失败。
7. 超时和浏览器异常能够转换为结构化错误。
8. 验证结果中的敏感信息不会出现在日志和响应中。
9. revision 更新不会覆盖历史验证记录。
10. 前端页面能正确展示验证中、成功和失败状态。

## 八、性能和并发要求

1. 普通资产列表和详情接口 P99 目标小于 80ms（不包含实际浏览器验证耗时）。
2. 列表接口必须分页，禁止无分页返回全量资产。
3. 使用 SQLAlchemy eager loading 或批量查询避免 N+1。
4. 禁止在循环中执行阻塞数据库或网络 IO。
5. 浏览器验证不得阻塞 FastAPI 事件循环；使用项目已有的异步方式或受控后台执行方式。
6. 单个项目的验证并发必须有限流，避免浏览器资源耗尽。
7. 每个请求、浏览器操作和后台任务都必须支持取消。
8. 失败后不得无限重试。

## 九、安全红线

- 所有对外接口必须校验认证和项目权限。
- 所有 URL 必须执行域名白名单和 SSRF 防护。
- 禁止访问云元数据地址、内网管理地址和未授权端口。
- 禁止把 Cookie、Token、密码和 Authorization 写入日志、DOM、截图或错误响应。
- 不允许通过页面步骤中的 Python 代码执行任意系统命令。
- 不允许把任意请求头、代理地址或文件路径直接传给浏览器。
- 证据文件必须检查项目归属和访问权限。
- 不得新增第三方依赖。

## 十、验收标准

以下条件必须全部满足，否则任务不算完成：

1. 不调用 LLM 也能完成页面、元素、步骤和场景的手工配置。
2. 页面和元素可以通过 Playwright 进行受控验证。
3. 定位器验证返回匹配数量、可见性、可操作性、实际 URL 和 DOM 指纹。
4. 非唯一定位器不能标记为已验证。
5. 主定位器、备用定位器和 iframe 配置可保存并可验证。
6. 所有 API 都有认证、项目隔离和结构化错误。
7. 所有资源引用关系有删除保护。
8. 验证过程不会阻塞 API 事件循环或泄漏浏览器资源。
9. 敏感信息不会出现在日志、响应和证据中。
10. 迁移可以在空数据库和已有一期数据库上执行。
11. 后端测试通过，前端测试和构建通过。
12. 现有一期接口自动化功能没有回归。
13. 不引入 AI、browser-use、Playwright MCP 或正式 UI actuator。

## 十一、交付规则

完成后请输出：

1. 实际修改文件清单。
2. 数据模型和 API 摘要。
3. 关键设计决策和未实现边界。
4. 执行过的测试命令及结果。
5. 未解决问题和风险。
6. 手工验收步骤。

不要修改无关文件，不要删除用户已有改动，不要提交密钥、Cookie、测试账号密码或真实业务数据。
