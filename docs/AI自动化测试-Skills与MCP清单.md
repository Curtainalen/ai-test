# AI 自动化测试平台 Skills 与 MCP 清单

> 用途：为后续开发、Agent 编排和执行器建设提供统一参考。
> 整理来源：本地 `WHartTest-master/WHartTest_Skills`、`WHartTest-master/WHartTest_MCP`，以及 GitHub 公共仓库信息。
> GitHub 信息核验日期：2026-08-31。仓库热度会变化，正式引入前仍需锁定版本、许可证和安全扫描结果。

## 1. 总体建议

建议采用以下组合：

```text
LLM/Agent
  -> 平台内部受控 Tool API（权限、项目归属、审批、幂等、审计、脱敏）
  -> Skills（业务工作流说明）
  -> MCP Adapter（可选外部协议层）
  -> API 执行器 / UI actuator / 报告服务
```

MCP 不应直接访问数据库，也不应绕过平台 API 调用浏览器或目标系统。Skills 负责告诉 Agent“什么时候查、什么时候建、如何确认和如何处理失败”；MCP/Tool 只负责调用经过权限控制的原子能力。

推荐优先级：

1. 先完善平台内部 REST/Tool API，再提供 MCP 适配器。
2. 首期直接复用 Playwright 执行能力，浏览器探索和正式回归分离。
3. Agent 默认只读；创建、修改、执行和删除均需审批或明确授权。
4. 不把 WHartTest 的默认密钥、硬编码地址、直接数据库访问代码复制到新平台。

## 2. WHartTest Skills 清单

| Skill | 主要能力 | 在本项目中的定位 | 建议期次 |
|---|---|---|---|
| `api-automation` | 模块、环境、变量、接口、调试、用例、标签、套件、同步、报告 | 直接转化为本平台接口自动化工作流规范；底层调用改为当前 FastAPI Tool API | 一期 |
| `ui-automation` | UI 模块、页面、元素、步骤、用例、执行记录、错误分析 | 作为 UI 资产管理和失败修复的业务 Skill；只保存人工确认后的定位器 | 二期 |
| `browser-use` | CDP 浏览器导航、交互、元素抓取、截图和页面探索 | 受控探索器；必须绑定域名、起始 URL、步数、允许操作和测试数据 | 二期 |
| `playwright-skill` | Playwright 页面结构读取、表单、登录、截图、浏览器操作 | browser-use 获取不到稳定元素时的 DOM/定位器兜底；也可用于执行器测试 | 二期 |
| `playwright-cli` | 标准化 CLI 浏览器会话、快照、截图、Trace、Storage State | 本地调试和人工复现工具；不作为服务端正式执行主链路 | 二期/研发工具 |
| `url-reader` | URL、Markdown、JSON、Swagger/OpenAPI/Redoc 读取和解析 | 作为 OpenAPI 远程导入前的读取器；必须配合 URL 白名单和 SSRF 防护 | 一期 |
| `whart-test` | 项目、模块、功能用例、截图、项目文件增删改查 | 当前平台的测试管理能力映射参考；新平台优先走自身项目/需求/报告 API | 一期 |
| `drawio` | 生成可编辑 `.drawio` 图表，可导出 PNG/SVG/PDF | 开发文档和架构图辅助工具，不属于测试执行依赖 | 可选 |
| `weknora-kb` | WeKnora 知识库搜索 | 与当前方案“显式需求上下文、不使用隐式 RAG/Embedding”冲突 | 首版不引入 |

### 2.1 Skill 协作规则

#### 接口自动化

```text
查询项目/模块/环境
  -> 不存在才创建资源
  -> 导入或创建接口
  -> 先 Preview/Run 调试
  -> 编排变量、提取、断言和步骤
  -> 人工确认场景版本
  -> 创建任务/套件执行
  -> 查询不可变报告
  -> 失败时读取步骤证据并提出修复候选
```

接口 Skill 必须支持：`${var}` 主语法、旧 `{{var}}` 兼容读取、变量来源追踪、敏感变量标记、写操作不自动重试、缺失变量结构化报错。

#### UI 自动化

```text
定义目标和探索边界
  -> browser-use 受控探索
  -> Playwright/DOM 验证元素
  -> 保存稳定定位器资产
  -> 组装候选步骤和场景
  -> 人工确认
  -> 独立 actuator 隔离执行
  -> 保存截图/Trace/DOM/日志
  -> 失败诊断和人工修复
```

定位器优先级建议：`data-testid`/稳定 id -> role + name -> label/name/placeholder -> 稳定 CSS -> XPath。禁止仅凭截图猜选择器，禁止直接把探索结果当作正式用例执行。

## 3. WHartTest MCP 清单

WHartTest 的 `WHartTest_MCP/WHartTest_tools.py` 是 FastMCP 服务，默认使用 streamable HTTP 运行在 8006；`ms_mcp_api.py` 运行在 8007，面向外部 MS 测试平台。

### 3.1 WHartTest Tools 能力

| 能力组 | 工具 | 当前平台建议 |
|---|---|---|
| 项目 | 获取项目名称和 ID | 映射为 `list_projects`，必须按当前用户权限过滤 |
| 模块 | 获取模块及 ID | 映射为需求模块/UI 模块/用例分组查询，不能混淆资产类型 |
| 用例元数据 | 获取用例等级、测试类型 | 使用平台枚举 API，写入前校验 |
| 用例查询 | 获取用例列表、详情 | 映射为测试场景和报告查询，增加 project scope |
| 用例写入 | 保存、编辑功能测试用例 | 只能写入候选版本；正式执行前必须有确认状态和 revision |
| 截图 | 保存单张/批量操作截图 | 改为受控文件上传；校验 file_id 项目归属和引用关系 |
| 图表 | 展示/编辑 diagram | 可作为研发辅助工具；不进入首期测试主链路 |

### 3.2 MS 测试用例 MCP

`ms_mcp_api.py` 提供：项目、模块、用例等级、测试步骤数据生成和功能用例保存。它依赖外部 MS API 的访问密钥和加密协议。

建议仅作为企业集成适配器，不放入平台核心域：

- 独立部署和独立凭据。
- 只允许通过平台的审批后同步任务触发。
- 不让 LLM 直接接触 MS 密钥。
- 同步必须保存请求、响应摘要、映射关系、失败原因和重试状态。

## 4. 本项目建议实现的内部 Tool API

MCP 应包在这些内部服务之上，而不是另造一套数据模型。

### 4.1 只读工具

```text
project.list / project.get
requirement.list_versions / requirement.get_modules / requirement.get_coverage
api.list_modules / api.list_interfaces / api.get_interface
api.list_environments / api.list_variables
api.get_debug_history / api.get_report
ui.list_pages / ui.get_page / ui.list_elements
execution.get_status / execution.get_steps / report.get_detail
```

### 4.2 候选生成工具

```text
requirement.review_testability
api.suggest_domains
api.generate_scenario_candidate
ui.generate_scenario_candidate
ui.suggest_locator_repair
```

这些工具只生成候选 JSON，不直接修改正式资产，不直接创建可执行任务。

### 4.3 需要审批的写入工具

```text
requirement.confirm_module / requirement.confirm_review
api.create_or_update_interface
api.create_or_update_scenario
ui.create_or_update_page / ui.create_or_update_element
ui.create_or_update_scenario
suite.create_or_update
approval.submit / approval.approve / approval.reject
```

### 4.4 明确受控的执行工具

```text
api.preview_request
api.run_debug_request
scenario.run
suite.run
ui.explore_bounded
ui.run_confirmed_scenario
execution.cancel
report.diagnose_failure
```

所有执行工具都必须校验：用户权限、项目归属、场景确认状态、环境白名单、并发配额、审批状态、超时和幂等键。

## 5. GitHub 可复用项目

以下项目通过 GitHub 公共 API 核验，适合作为依赖或实现参考。星标只代表项目关注度，不代表适合直接用于生产。

| 项目 | 许可证/规模信息 | 适用场景 | 建议 |
|---|---|---|---|
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | Apache-2.0；微软官方 Playwright MCP Server | AI 调用浏览器、页面快照、元素操作和测试辅助 | 二期优先评估；使用固定版本并限制目标域名 |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | MIT；AI 浏览器自动化框架 | UI 受控探索和自然语言任务规划 | 二期评估；探索与正式执行隔离，不能直接作为生产回归执行器 |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 官方 MCP servers 集合 | MCP 协议实现、服务模板和安全边界参考 | 参考官方实现；按需选择，不整体引入 |
| [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | Apache-2.0；Python MCP Server/Client 框架 | 为 FastAPI 平台封装 streamable HTTP/stdio MCP | 一期后半段或二期引入；先定义平台 Tool 契约 |
| [MCPJam/inspector](https://github.com/MCPJam/inspector) | MCP 调试/检查工具 | 调试工具列表、输入 Schema、调用结果和 MCP 连接 | 研发测试工具；不作为生产依赖 |
| [Tencent/BrowserSkill](https://github.com/Tencent/BrowserSkill) | MIT；真实登录浏览器的 Agent 浏览器能力 | 研究登录态浏览器、扩展和 CLI 集成 | 暂不引入生产；真实登录态、Cookie 和数据泄露风险较高 |

### 5.1 不建议直接引入的 GitHub 结果

- 不要因为 star 高就直接引入通用浏览器 Agent；先验证许可证、维护状态、沙箱、网络边界和凭据处理。
- 不要把多个浏览器主控同时接入一个会话；browser-use、Playwright MCP 和正式 actuator 必须有明确角色。
- 不要把 MCP server 当成权限系统；权限、审批、审计、脱敏和幂等必须由本平台后端掌握。
- 不要把第三方示例中的默认 API Key、默认 URL 或本地文件访问逻辑复制到生产环境。

## 6. 版本与部署建议

### 一期

- 保留现有 FastAPI + RQ + Redis + PostgreSQL 架构。
- 先实现内部 Tool API 和 API Skill。
- MCP 先提供只读查询、Preview 和报告查询；写入工具暂不开放给自由对话 Agent。
- `url-reader` 只处理白名单 URL，导入文件走平台受控上传。

### 二期

- 引入 Playwright MCP 或 browser-use 其中一个作为探索主控，另一个仅在验证后作为兜底，不建议两者同时承担同类职责。
- actuator 继续使用 Python Playwright async 执行确认后的场景。
- MCP 连接配置按项目隔离，记录 server name、版本、工具清单、调用耗时和错误。

### 三期

- 开放完整 Agent 工具链，但继续保持审批、审计、租约、配额和失败停止。
- 使用 MCP Inspector 做协议级回归测试。
- 对所有外部 MCP server 做依赖锁定、镜像扫描、SBOM、权限最小化和网络 egress 限制。

## 7. 安全基线

1. MCP server 不保存明文平台密钥；凭据由后端密钥管理或环境注入。
2. 工具参数必须带 `project_id` 或从已认证上下文派生，禁止由模型任意跨项目访问。
3. 所有写操作使用 `revision`/幂等键，拒绝过期更新和重复执行。
4. 所有浏览器操作必须经过域名白名单、动作白名单和超时限制。
5. 禁止工具读取未授权本地文件、任意 URL、数据库连接串和环境变量。
6. 请求、响应、截图、Trace、DOM、Prompt 和工具返回值都执行统一脱敏。
7. 工具错误返回结构化错误码，不把堆栈、密钥或完整上游响应直接暴露给模型。
8. MCP 工具清单变更需要审计和回归测试，防止工具投毒或描述漂移。

## 8. 落地顺序

```text
P0  固定本项目 Tool API 契约、权限和脱敏规范
P1  从 WHartTest api-automation skill 改写当前平台 API Skill
P1  接入 FastMCP 只读适配器，完成接口/需求/报告查询
P1  增加 Preview、候选场景生成和人工审批工具
P2  接入 Playwright MCP 或 browser-use 做受控探索
P2  完成 ui-automation skill 和 actuator 闭环
P3  接入套件、定时回归、Agent、Inspector 和运营治理
```

## 9. 参考来源

- `D:\Project\WHartTest-master\WHartTest_Skills\manifest.json`
- `D:\Project\WHartTest-master\WHartTest_Skills\api-automation-skill\SKILL.md`
- `D:\Project\WHartTest-master\WHartTest_Skills\ui-automation-skill\SKILL.md`
- `D:\Project\WHartTest-master\WHartTest_Skills\browser-use\SKILL.md`
- `D:\Project\WHartTest-master\WHartTest_Skills\playwright-skill\SKILL.md`
- `D:\Project\WHartTest-master\WHartTest_MCP\WHartTest_tools.py`
- `D:\Project\WHartTest-master\WHartTest_MCP\ms_mcp_api.py`
- `D:\Project\WHartTest-master\WHartTest_MCP\README.md`
- GitHub 项目链接见上表。
