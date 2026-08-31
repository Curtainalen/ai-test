# UI 自动化开发计划

## 1. 文档目的

本文基于以下方案文档和 WHartTest 代码现状整理：

- `D:\桌面\AI自动化测试.md`
- `D:\桌面\AI自动化测试-Skills与MCP清单.md`
- `D:\桌面\AI自动化测试-两三期开发计划.md`
- `D:\Project\WHartTest-master`

本文不改变原方案中的产品约束，只将 UI 自动化拆分为更细的开发阶段。核心目标是：先完成一条不依赖 AI 也能稳定运行的 UI 自动化闭环，再逐步接入 AI。

## 2. 总体原则

UI 自动化不是让 AI 直接点击并执行回归，而是：

```text
受控探索产出候选资产
  -> 程序验证定位器
  -> 人工确认资产和场景
  -> 确定性的 Playwright 执行器正式执行
  -> 采集证据并生成报告
```

必须遵循以下原则：

1. 探索范围必须受控，不能默认全量扫描站点。
2. AI 生成的页面、元素、定位器、步骤、数据和场景均为候选内容。
3. 未经人工确认的内容不能进入正式执行。
4. 探索会话和正式回归执行必须隔离。
5. 定位器不能仅根据截图猜测，必须通过页面结构和实际匹配结果验证。
6. 失败修复不能静默修改资产，也不能未经确认自动重跑。
7. 敏感数据不能进入 LLM 上下文、日志、截图、Trace 或 DOM 快照。

## 3. 文档中 AI 的具体作用

### 3.1 受控页面探索

AI 根据用户提供的测试目标，在限定范围内规划页面探索路径。

探索任务必须定义：

- 允许访问的域名
- 起始 URL
- 允许访问的页面
- 最大探索步数
- 允许的操作类型
- 禁止的操作类型
- 测试账号和测试数据
- 会话超时和资源限制

提交、删除、支付、发信等有副作用的操作必须使用测试数据，并获得明确授权。

### 3.2 页面和元素理解

AI 根据页面 URL、页面快照、可访问性树和 DOM 结构，识别当前页面及与目标相关的元素。

AI 输出的元素必须经过程序验证，至少验证：

- 定位器语法有效
- 匹配数量是否为 1
- 元素是否可见
- 元素是否可操作
- 当前 URL 是否符合预期
- 是否处于 iframe 中

### 3.3 定位器候选生成

定位器推荐优先级：

```text
data-testid / 稳定 id
  -> role + name
  -> label / name / placeholder
  -> 稳定 CSS
  -> XPath
```

应避免：

- 深层 `:nth-child()` 路径
- 绝对 XPath
- 构建产物 hash class
- 时间戳、数量、用户名等动态文本
- 只依赖截图坐标或视觉猜测

### 3.4 UI 场景编排

用户可以用自然语言描述业务目标，AI 结合已确认的页面、元素和定位器资产，生成候选场景，包括：

- 前置条件
- 页面访问
- 操作步骤
- 输入数据
- 断言
- 预期结果
- 失败时的证据采集要求

AI 生成结果不能直接创建可执行任务。人工必须确认场景版本、步骤顺序、测试数据、预期结果和允许执行范围。

### 3.5 失败分析和修复建议

失败后，AI 可以根据失败步骤、错误信息、截图、DOM 快照和 Trace，提出问题分类和修复建议。

至少支持以下分类：

- 产品缺陷
- 定位器失效
- 页面加载或环境异常
- 认证失效
- 测试数据异常
- 执行器异常
- 预期结果不一致

AI 只能生成局部修复候选。人工确认后创建新的定位器或场景 revision，并由人工决定是否重新执行。

## 4. WHartTest 能力对照

### 4.1 数据层次

WHartTest 的 UI 自动化采用以下层次：

```text
UI 模块
  -> 页面
    -> 元素
      -> 页面步骤
        -> UI 测试用例
          -> 执行记录
```

主要模型位于：

`D:\Project\WHartTest-master\WHartTest_Django\ui_automation\models.py`

模型职责如下：

| 模型 | 作用 |
|---|---|
| `UiPage` | 保存项目、模块、页面名称和 URL |
| `UiElement` | 保存主定位器、备用定位器、等待时间和 iframe 配置 |
| `UiPageSteps` | 保存可复用的页面操作集合 |
| `UiPageStepsDetailed` | 保存点击、输入、断言、等待、变量等具体动作 |
| `UiTestCase` | 组合多个页面步骤形成完整用例 |
| `UiExecutionRecord` | 保存执行状态、步骤结果、截图、Trace、日志和错误 |

### 4.2 采集和定位

WHartTest 的 Skill 规定：

```text
browser-use 默认采集
  -> playwright-skill 兜底
  -> ui-automation 保存元素和步骤
```

其中：

- `browser-use` 负责页面访问、元素抓取和交互识别。
- `playwright-skill` 在默认采集无法稳定获取元素时提供 DOM 和定位器兜底。
- `ui-automation-skill` 负责查询、创建、编辑页面、元素、步骤和用例。

参考文件：

- `D:\Project\WHartTest-master\WHartTest_Skills\ui-automation-skill\SKILL.md`
- `D:\Project\WHartTest-master\WHartTest_Skills\browser-use\SKILL.md`
- `D:\Project\WHartTest-master\WHartTest_Skills\playwright-skill\SKILL.md`

WHartTest 的定位器模型支持一个主定位器和两个备用定位器。正式执行时依次尝试主定位器和备用定位器，并支持 iframe。

### 4.3 执行和结果

WHartTest 使用 Python Playwright 执行器，主要能力包括：

- 独立浏览器上下文
- 页面导航
- 点击、输入、选择、悬停、键盘操作
- iframe 定位
- 元素和页面断言
- 主定位器和备用定位器切换
- 步骤级截图
- Trace 和日志
- WebSocket 结果回传

参考文件：

`D:\Project\WHartTest-master\WHartTest-master\WHartTest_Actuator\executor.py`

实际路径为：

`D:\Project\WHartTest-master\WHartTest_Actuator\executor.py`

### 4.4 可借鉴和不可直接复制的部分

可借鉴：

- 页面、元素、页面步骤、用例的分层模型
- 主定位器和备用定位器
- 页面步骤复用
- 元素引用保护
- 独立 Playwright 执行器
- 步骤级执行记录和证据

不可直接复制：

- Django/Vue 整套工程
- 默认密钥和默认地址
- 直接数据库访问方式
- 未审查的旧依赖
- 未经平台权限控制的 MCP 写入逻辑

## 5. 分阶段开发计划

## 阶段一：UI 领域模型和资产 API

本阶段不接入 AI。

### 开发内容

实现以下资产：

```text
UiModule
UiPage
UiElement
UiPageStep
UiPageStepDetail
UiScenario
UiScenarioStep
```

每项资产至少包含：

- `project_id`
- 创建人和更新时间
- 状态
- revision 或版本号
- 归属关系
- 审计信息

元素资产至少包含：

```json
{
  "name": "登录按钮",
  "page_id": "page-id",
  "primary_locator": {
    "type": "role",
    "value": "button",
    "name": "登录"
  },
  "fallback_locators": [],
  "frame_locator": null,
  "expected_match_count": 1,
  "verified": false,
  "verified_url": null,
  "dom_fingerprint": null,
  "source": "manual"
}
```

### API 范围

- 页面增删改查
- 元素增删改查
- 页面步骤增删改查
- 场景增删改查
- 资产引用关系校验
- 项目和环境权限校验
- 删除保护

### 验收标准

- 资产只能在当前项目范围内访问。
- 被引用的元素、页面步骤不能直接删除。
- 场景可以固定引用某个资产 revision。
- API 对非法定位器类型、越权项目和无效引用返回结构化错误。

## 阶段二：手工录入和定位器验证

本阶段仍不接入 AI。

### 开发内容

实现页面和定位器验证接口：

```text
输入：页面 URL + 定位器
输出：
  - 是否成功
  - 匹配数量
  - 是否可见
  - 是否可操作
  - 实际页面 URL
  - DOM 摘要
  - 验证截图
```

支持的定位器类型至少包括：

- test id
- id
- role
- label
- placeholder
- name
- CSS
- XPath

### 验收标准

- 定位器匹配数量不是 1 时不能标记为已验证。
- 验证超时、页面不可访问和 iframe 错误均可区分。
- 验证结果保存 URL、时间、DOM 指纹和证据引用。
- 验证失败不会自动修改已有定位器。

## 阶段三：受控浏览器探索会话

本阶段先支持人工操作或固定脚本驱动，不要求 AI 接管浏览器。

### 开发内容

实现探索会话：

```text
创建探索会话
  -> 校验域名白名单
  -> 打开起始 URL
  -> 页面导航
  -> 获取页面快照
  -> 获取 DOM / accessibility tree
  -> 选择元素
  -> 验证定位器
  -> 保存探索证据
  -> 人工确认
```

### 安全边界

- 域名白名单
- 起始 URL 限制
- 页面访问范围
- 最大操作步数
- 操作白名单
- 禁止操作列表
- 测试账号和测试数据
- 会话超时
- 截图、DOM 和日志脱敏
- 探索会话与正式执行隔离

### 验收标准

- 越权域名和禁止动作会被平台拒绝。
- 每次探索都能查询操作日志和证据。
- 探索结果不会自动生成正式场景。
- 能从探索结果中人工选择页面和元素并保存。

## 阶段四：正式 Playwright actuator

本阶段实现不依赖 AI 的正式执行能力。

### 执行链路

```text
人工确认的 UI 场景
  -> 创建执行任务
  -> RQ 调度
  -> actuator 获取任务租约
  -> 创建独立 Browser Context
  -> 加载受控登录态
  -> 执行步骤
  -> 每步上报状态
  -> 保存截图 / DOM / Trace / 日志
  -> 生成执行报告
```

### 执行器要求

- 每个任务使用独立 Browser Context。
- 任务领取需要租约、心跳和超时回收。
- 定位器失败不能静默替换正式资产。
- 只有明确允许的幂等操作才允许重试。
- storage state 必须绑定项目、环境、域名和有效期。
- 输入数据、日志和证据需要脱敏。
- 执行器与探索浏览器不能共享控制会话。

### 验收标准

- 支持页面导航、点击、输入、选择、等待和断言。
- 支持主定位器和备用定位器。
- 支持 iframe。
- 支持步骤级成功、失败、跳过和取消状态。
- 失败步骤至少关联错误、截图、DOM 快照或 Trace。
- actuator 断线后任务最终进入可解释状态。

## 阶段五：完成无 AI 的 UI 全流程

这是第一阶段 UI 自动化的正式交付目标。

```text
创建项目和环境
  -> 配置页面
  -> 验证页面可访问
  -> 配置元素
  -> 验证定位器
  -> 创建页面步骤
  -> 配置操作和断言
  -> 组合 UI 场景
  -> 人工确认场景
  -> 创建异步任务
  -> actuator 执行
  -> WebSocket 回写进度
  -> 查看步骤结果
  -> 查看截图 / DOM / Trace
  -> 查看失败详情
```

### 首条验收场景

建议使用登录主流程：

```text
打开登录页
  -> 输入用户名
  -> 输入密码
  -> 点击登录
  -> 验证进入首页
```

本阶段明确不实现：

- AI 自动探索
- AI 自动生成定位器
- AI 自动生成场景
- AI 自动修复
- 未经确认自动重跑
- 全站扫描

## 阶段六：接入 AI 探索和定位

基础执行闭环稳定后，再接入 AI。

### 交互流程

```text
用户提出测试目标
  -> AI 读取当前页面快照
  -> AI 提出下一步探索动作
  -> 平台检查动作白名单
  -> 浏览器执行动作
  -> 返回页面结构和结果
  -> AI 提取页面、元素和定位器候选
  -> 程序验证定位器
  -> 人工确认
  -> 保存正式资产 revision
```

AI 不直接负责：

- 权限判断
- 域名校验
- 浏览器底层执行
- 定位器最终验证
- 正式资产写入
- 正式回归执行

## 阶段七：接入 AI 场景编排和失败修复

### 场景编排

```text
已确认页面和元素资产
  -> AI 生成候选场景
  -> 人工编辑和确认
  -> 创建正式执行任务
```

### 失败修复

```text
执行失败
  -> 获取失败步骤证据
  -> AI 分类问题
  -> AI 生成候选修复
  -> 人工确认
  -> 创建新 revision
  -> 人工决定是否重跑
```

## 6. 推荐的内部 Tool API

### 只读工具

```text
ui.list_modules
ui.list_pages
ui.get_page
ui.list_elements
ui.get_element
ui.list_page_steps
ui.get_page_step
ui.list_scenarios
ui.get_scenario
ui.get_exploration
ui.get_execution
ui.get_report
```

### 验证工具

```text
ui.verify_page
ui.verify_locator
ui.inspect_dom
ui.inspect_accessibility_tree
```

### 候选生成工具

```text
ui.explore_bounded
ui.generate_locator_candidate
ui.generate_scenario_candidate
ui.suggest_locator_repair
```

这些工具只能生成候选结果或探索结果，不能直接修改正式资产或创建可执行任务。

### 需要审批的写入工具

```text
ui.confirm_page
ui.confirm_element
ui.confirm_locator
ui.create_or_update_page
ui.create_or_update_element
ui.create_or_update_page_step
ui.create_or_update_scenario
approval.submit
approval.approve
approval.reject
```

### 受控执行工具

```text
ui.run_confirmed_scenario
ui.cancel_execution
ui.get_execution_status
```

## 7. 需要冻结的架构决策

1. 探索主控在 `browser-use` 和 Playwright MCP 中二选一，不能让多个控制方同时操作同一浏览器会话。
2. 页面结构验证统一使用 Playwright DOM 或 accessibility API。
3. 正式执行统一使用 Python Playwright actuator。
4. 所有 AI 结果都必须有候选状态、人工确认记录和 revision。
5. UI 资产必须与项目、环境和目标域名绑定。
6. 报告必须保存执行时的场景、页面、元素和定位器 revision。
7. 失败修复采用局部重采集，不进行默认全站重新扫描。
8. 截图、Trace、DOM 快照使用受控文件存储，并实施访问控制、脱敏和保留策略。

## 8. 当前仓库基线

当前 `D:\Project\ai-test` 已有接口自动化一期基础，包括项目、环境、需求、OpenAPI、异步任务、WebSocket 和报告相关能力。

当前 `D:\Project\ai-test\actuator\README.md` 明确 UI actuator 仍是后续预留，尚未实现 UI 自动化执行。因此 UI 开发应从领域模型、资产 API 和执行边界开始，不应假设现有仓库已经具备 WHartTest 的 UI 能力。

## 9. 第一批开发任务建议

建议首先拆出以下开发任务：

1. UI 资产数据库模型和迁移。
2. 页面、元素、页面步骤和场景 REST API。
3. 项目、环境和目标域名权限校验。
4. 定位器验证服务。
5. UI 资产管理前端页面。
6. 页面步骤和场景编辑器。
7. Playwright actuator 任务协议。
8. actuator 浏览器上下文和基础动作执行。
9. 步骤结果、截图、DOM、Trace 和日志上传。
10. WebSocket UI 执行进度和失败详情。
11. 登录主流程端到端验收。
12. 在无 AI 闭环稳定后，再实现受控 AI 探索。

## 10. 完成定义

UI 自动化前置阶段完成的标准是：不调用 LLM，用户仍可以手工配置页面、元素、定位器、步骤和场景，人工确认后创建异步任务，由独立 actuator 在隔离浏览器上下文中执行，并在前端看到实时进度、步骤结果和可审计证据。

只有达到这个标准后，才进入 AI 探索、AI 定位器候选、AI 场景编排和 AI 失败修复阶段。
