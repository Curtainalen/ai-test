# AI 自动化测试二期开发实施计划

## 1. 文档定位

本文将《AI自动化测试-两三期开发计划.md》的第二期拆分为可执行、可验收的开发顺序，适用于当前 `ai-test` 项目。

二期目标不是增加一个 AI 按钮，而是交付以下闭环：

```text
需求模块
  -> AI 测试点评审
  -> 接口/UI 候选生成
  -> 人工审核
  -> 受控执行
  -> 截图、DOM、Trace、日志和报告
  -> 失败诊断和修复候选
  -> 新 revision 再审核
```

二期最终应同时支持接口自动化和 UI 自动化，并保证所有 AI 结果均为候选内容，未经人工确认不能执行。

## 2. 当前基础和复用原则

当前项目已经存在并应继续复用：

- JWT 登录、项目成员和项目权限校验
- 测试环境及 Base URL 校验
- SQLAlchemy Async、Alembic、统一错误响应
- Redis/RQ 队列和 Worker
- UI 模块、页面、元素、页面步骤、场景模型
- UI 探索会话、执行任务和报告模型
- Playwright 页面/定位器验证服务
- UI actuator 独立 Browser Context
- 脱敏、证据引用和 WebSocket 状态推送
- React、TypeScript、Vite、Ant Design 页面框架

禁止：

- 复制 WHartTest 的 Django/Vue/直接数据库架构
- 引入 browser-use、Playwright MCP 或新的第三方依赖作为第二套执行器
- 引入 RAG、Embedding、向量数据库
- AI 直接写入正式资产
- AI 直接创建正式执行任务
- 默认全站扫描或生产环境写操作

## 3. 总开发顺序

必须按以下顺序推进，不能跳过前置依赖：

```text
阶段 0  一期基线和二期口径冻结
   ↓
阶段 1  LLM 统一网关和模型版本
   ↓
阶段 2  AI 需求可测性评审
   ↓
阶段 3  UI 页面元素自动采集
   ↓
阶段 4  自动生成并验证 Locator
   ↓
阶段 5  AI 连续探索页面
   ↓
阶段 6  接口/UI 场景候选与人工审核
   ↓
阶段 7  UI actuator、证据和报告增强
   ↓
阶段 8  失败诊断、Locator 修复候选和需求覆盖
   ↓
阶段 9  全链路验收、性能和安全测试
```

## 4. 阶段 0：一期基线和二期口径冻结

### 目标

确保二期开发不会破坏一期接口自动化闭环，并冻结二期的产品边界。

### 工作内容

- 运行一期后端单元测试、API 测试和前端构建
- 验证 Docker Compose、后端健康检查和 `8080` 前端入口
- 验证项目隔离、环境权限、场景确认和执行幂等
- 确定首期支持的 LLM 协议
- 确定 UI 浏览器，建议先支持 Chromium
- 确定 UI 允许动作、禁止动作和需要审批的动作
- 确定单项目并发、单任务步数、页面数量和总超时
- 清理旧文档中与当前方案冲突的 RAG/Embedding 口径

### 交付物

- 二期范围说明
- 状态枚举和错误码清单
- 一期回归测试基线
- UI 探索安全策略

### 通过条件

- 一期测试全部通过
- 迁移可在空库和已有数据库执行
- 不改变已有接口自动化契约

## 5. 阶段 1：LLM 统一网关和模型版本

### 目标

所有 AI 调用统一经过一个可审计、可限流、可脱敏的网关。

### 建议目录

```text
backend/app/services/llm/
  gateway.py
  adapters/
    openai_chat.py
    openai_responses.py
    compatible.py
  schemas.py
  usage.py
  redaction.py
```

### 开发顺序

1. 复用当前模型配置和 API Key 掩码逻辑。
2. 抽象统一 `chat()`、结构化输出和超时接口。
3. 先实现 OpenAI Chat/Responses 兼容协议。
4. 再实现自定义 OpenAI-compatible endpoint。
5. 最后扩展 Anthropic、Gemini、Azure、Bedrock 适配器。
6. 增加模型配置 revision 和 LLM 调用记录。

### 必须实现

- 连接超时、读取超时和总超时
- 项目级并发限制和限流
- 有限重试，不对写操作无限重试
- Token 用量记录
- 供应商未返回用量时记录 `usage_unknown`
- API Key 不回传、不进入日志和 Prompt
- Prompt、响应和错误统一脱敏
- 每次候选生成绑定模型配置 revision

### 通过条件

- 模型切换不影响历史候选和报告
- 401、403、404、429、超时和上游 5xx 有明确错误分类
- API Key 在响应、日志和前端页面中均不泄露

## 6. 阶段 2：AI 需求可测性评审

### 目标

让 AI 根据用户明确选择的需求文档版本和需求模块，生成测试点和风险评审结果。

### 建议模型

```text
RequirementReview
RequirementTestPoint
RequirementCoverage
```

### AI 输出

```json
{
  "module_id": "module-001",
  "test_points": [
    {
      "id": "tp-001",
      "title": "正确账号密码登录",
      "preconditions": ["账号已启用"],
      "test_data_refs": ["secret://test-user"],
      "expected_result": "进入工作台",
      "risk": "medium"
    }
  ],
  "ambiguities": [],
  "acceptance_suggestions": []
}
```

### 约束

- 只能读取用户选中的需求版本和模块
- 不读取其他项目或未授权资源
- 结果只能是候选评审
- 测试点必须有稳定 ID
- 后续接口/UI 场景引用测试点 ID
- 需求版本变化后，相关场景标记为 `待复核`

### 通过条件

- 可生成、编辑、确认和驳回测试点
- 测试点能关联接口场景和 UI 场景
- 需求版本变化能计算受影响场景

## 7. 阶段 3：UI 页面元素自动采集

### 目标

先得到真实页面结构，再让 AI 使用这些结构，禁止 AI 臆造元素和定位器。

### 建议模型

```text
UiCollectionSession
UiCollectionSnapshot
UiCollectedPage
UiCollectedElement
UiLocatorCandidate
```

如果首版不拆表，可将快照结构化保存在现有探索步骤 JSON 中，但必须保留唯一 `snapshot_id`。

### 单个元素必须包含

- `element_key`
- 页面 key 和 snapshot ID
- tag、role、accessible name、text
- test_id、id、name、label、placeholder
- visible、enabled、actionable、checked
- iframe `frame_path`
- locator candidates
- DOM fingerprint
- 证据引用

### Locator 候选优先级

```text
data-testid/test_id
  -> 稳定 id
  -> role + accessible name
  -> label
  -> name
  -> placeholder
  -> 稳定 CSS
  -> XPath
```

### 采集限制

- 页面数量上限
- 单页元素数量上限
- 最大深度
- 同源和允许路径限制
- iframe 数量限制
- 单页超时和总超时
- 禁止危险点击和写操作
- DOM、截图、文本统一脱敏

### 通过条件

- 能采集主页面和 iframe 元素
- 能返回 Accessibility Tree 和 DOM inventory
- 每个 locator candidate 绑定真实元素和 snapshot
- 跨项目无法读取采集结果

## 8. 阶段 4：自动生成并验证 Locator

### 目标

把“候选定位器”变成可验证、可追溯的定位器 revision。

### 验证流程

```text
读取 locator candidate
  -> 校验项目环境 URL
  -> 创建独立 Browser Context
  -> 定位 iframe
  -> 验证目标元素
  -> 记录匹配数、可见性、可操作性
  -> 保存实际 URL、fingerprint 和证据引用
```

### 验证成功条件

```text
match_count == 1
visible == true
actionable == true
```

### 主备 Locator

每个元素保存一个主定位器和多个备用定位器。主定位器失败时，继续验证备用定位器，但不能覆盖原正式定位器。

更新定位器必须：

- 创建新的 element revision
- 保留历史验证记录
- 保存验证前后 fingerprint
- 由人工确认后才替换正式 locator

### 通过条件

- 0 个匹配和多个匹配均不能标记为已验证
- iframe 成功和失败都能结构化记录
- 验证超时、页面异常和浏览器异常可区分
- 验证失败不会修改原正式资产

## 9. 阶段 5：AI 连续探索页面

### 目标

将当前“一次采集、一次生成”改造成多轮观察和决策循环。

### 状态机

```text
planning
  -> action_proposed
  -> policy_checked
  -> executing
  -> observation_saved
  -> planning
```

终态：

```text
completed / failed / canceled / timeout / waiting_approval
```

### 每轮 AI 输入

- 测试目标
- 当前 URL
- 当前页面 snapshot ID
- 当前真实元素 inventory
- 历史动作摘要
- 上一步执行结果
- 剩余步数和剩余时间
- 脱敏错误信息

### 每轮 AI 输出

```json
{
  "operation": "click",
  "target_element_key": "login_submit",
  "value": null,
  "reason": "提交登录表单",
  "expected": "进入工作台或显示登录错误"
}
```

### 动作白名单

```text
navigate、click、fill、select、hover、press、check、uncheck、wait、assert_visible、assert_text、assert_url
```

禁止输出 Python、JavaScript、`evaluate`、shell 命令、代理配置和任意文件路径。

### 副作用控制

删除、支付、发信、提交订单、生产数据修改等动作默认需要人工审批。

### 通过条件

- AI 能完成至少一条登录或查询主流程
- 每轮动作都经过平台策略校验
- 连续探索可取消、超时和恢复
- 不会访问越权域名或未授权路径
- 不会把密码、Token、Cookie 放入模型上下文

## 10. 阶段 6：接口/UI 场景候选与人工审核

### 目标

统一接口和 UI 的候选生成、差异查看、人工确认和 revision 管理。

### 候选状态

```text
draft
  -> pending_review
  -> approved
  -> rejected
  -> superseded
```

### 候选内容

- 页面和模块
- 真实元素引用
- 主/备用定位器
- 页面步骤
- 接口步骤
- 输入数据引用
- 断言
- 需求测试点关联

### 审核页面必须支持

- 候选差异
- Locator 验证结果
- 页面/元素/步骤选择
- 步骤排序
- 输入数据和断言编辑
- 需求测试点覆盖
- 批量确认或驳回

确认后才创建正式场景，且必须重新校验项目归属和资源引用。

## 11. 阶段 7：UI actuator、证据和报告增强

### 目标

让确认后的 UI 场景可以安全执行，并产生不可变报告。

### 执行器要求

- 独立 Browser Context
- 任务租约、心跳和并发槽位
- 协作式取消
- 浏览器崩溃回收
- 步骤级状态、耗时和错误分类
- 主/备用 locator 执行策略
- iframe 执行
- 截图、DOM、Trace 和日志证据引用
- 所有证据脱敏

探索器和正式 actuator 不得共享浏览器实例或登录态。

### 报告必须固定

- 场景 revision
- 环境快照
- 模型配置 revision
- 实际 URL
- 每步动作和结果
- Locator 验证结果
- 截图、DOM、Trace 引用
- 脱敏错误和失败分类

历史报告不能随着场景更新而变化。

## 12. 阶段 8：失败诊断、Locator 修复候选和需求覆盖

### 失败分类

```text
产品缺陷
定位器失效
页面加载异常
认证失效
测试数据异常
环境异常
执行器异常
预期结果不一致
```

### AI 修复输入

- 失败步骤
- 错误分类和脱敏错误
- 当前 URL
- DOM 摘要
- 截图/Trace 引用
- 原 locator 验证记录
- 历史 locator revision

### AI 修复输出

只能是局部修复候选，不能直接修改正式元素：

```json
{
  "category": "locator_broken",
  "suggestions": [
    {
      "type": "role",
      "value": "button",
      "name": "登录",
      "evidence": "当前 AX Tree 中唯一匹配"
    }
  ]
}
```

### 需求覆盖

显示：

- 未覆盖
- 已生成候选
- 已确认
- 执行通过
- 执行失败
- 因需求变更待复核

## 13. 阶段 9：全链路验收

### 后端测试

- LLM 网关超时、限流、脱敏、用量和配置 revision
- 需求评审候选和测试点关联
- UI 采集项目隔离和页面边界
- Locator 唯一性、可见性、可操作性
- iframe 成功和失败
- 连续探索动作白名单和取消
- 浏览器崩溃、超时、断线回收
- 候选确认、revision 冲突和跨项目引用
- 报告不可变和需求覆盖

### 前端测试

- AI 评审加载、空状态和错误状态
- 探索中、等待审批、成功、失败和取消状态
- 元素和 Locator 验证结果展示
- 候选差异和批量确认
- 执行报告和证据引用
- 权限错误和脱敏错误提示

### 验收主流程

```text
创建项目和环境
  -> 上传并确认需求模块
  -> AI 生成测试点
  -> 启动 UI 受控探索
  -> 自动采集页面和元素
  -> AI 连续规划登录流程
  -> 自动生成并验证 Locator
  -> 人工确认 UI 场景
  -> Playwright actuator 执行
  -> 查看截图、DOM、Trace 和报告
  -> 模拟 Locator 失效
  -> 查看 AI 修复候选
  -> 创建新 revision 并重新审核
```

## 14. 推荐排期

按 8-10 周安排：

| 周期 | 主要交付 |
|---|---|
| 第 1 周 | 阶段 0：基线、范围、错误码和安全策略 |
| 第 2 周 | 阶段 1：LLM 网关和模型配置 revision |
| 第 3 周 | 阶段 2：需求评审、测试点和覆盖模型 |
| 第 4-5 周 | 阶段 3：UI 采集快照、AX/DOM、iframe 和候选 Locator |
| 第 6 周 | 阶段 4-5：Locator 批量验证和 AI 连续探索 |
| 第 7 周 | 阶段 6：接口/UI 候选和人工审核 |
| 第 8 周 | 阶段 7：actuator、证据和报告增强 |
| 第 9 周 | 阶段 8：失败诊断、修复候选和需求覆盖 |
| 第 10 周 | 阶段 9：全链路、性能、安全、迁移和容器验收 |

## 15. 二期完成标准

二期只有同时满足以下条件才算完成：

1. 同一个需求模块可以生成接口和 UI 候选场景。
2. AI 结果未经人工确认不能写入正式资产或执行。
3. UI 元素来自真实采集，不允许 AI 臆造 Locator。
4. Locator 必须通过唯一、可见、可操作验证。
5. 主/备用 Locator 和 iframe 均可配置、验证和执行。
6. 探索动作受域名、路径、步数、超时和白名单约束。
7. 探索与正式执行使用不同 Browser Context。
8. 超时、取消、断线、浏览器崩溃都有明确终态。
9. 密钥、Token、Cookie、密码和个人信息不进入 Prompt、日志、截图和报告。
10. 历史报告可追溯场景、需求和模型配置 revision。
11. 需求版本变化能标记受影响场景。
12. 一期接口自动化功能无回归。
13. 后端测试、前端测试、构建、迁移和 Docker 验收全部通过。

## 16. 当前建议的第一步

真正开始编码时，先做阶段 0 和阶段 1，然后立即做阶段 3 的“结构化 UI 采集”。

原因是：连续探索、自动生成 Locator、UI 场景编排都依赖真实页面元素。如果采集层不可靠，后面的 AI 只能生成看起来合理但无法执行的流程。
