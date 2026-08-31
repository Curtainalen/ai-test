# 一期架构与数据模型

## 服务边界

- `frontend`：React 18 + TypeScript + Ant Design，所有业务规则由后端裁决。
- `backend`：FastAPI REST/WebSocket，薄路由、service 层业务、SQLAlchemy Async 数据访问。
- `worker`：RQ Worker，运行文档解析与接口场景执行任务。
- `postgres`：资产、状态、步骤事实和不可变报告。
- `redis`：RQ 队列；数据库是断线恢复和最终状态的事实源。
- `nginx`：前端静态文件与 `/api`、`/ws` 反向代理。

## 核心实体

| 领域 | 实体 |
|---|---|
| 身份与隔离 | User、Project、ProjectMember、TestEnvironment |
| 需求资产 | RequirementDocument、DocumentVersion、ParseJob、ContentBlock、RequirementModule、RequirementModuleBlock |
| 接口资产 | ApiImport、ApiModule、ApiInterface、DebugRun |
| 场景 | TestScenario、ScenarioStep、ScenarioRequirement |
| 执行与报告 | ExecutionTask、ExecutionStep、TestReport、ReportStep |

所有项目资源带 `project_id`；可编辑聚合带 `revision`；审计实体带创建人和时间。文档版本、执行步骤事实、报告及报告步骤不可原地修改。

## 关键一致性

1. 调试与场景执行调用同一 `RequestEngine`。
2. WebSocket 首帧为数据库快照，后续推送状态变化；重连不会依赖丢失的内存事件。
3. 执行创建以 `(project_id, idempotency_key)` 唯一；报告以 `execution_id` 唯一。
4. 报告复制场景、需求、环境和步骤的执行时快照，不回查当前可变资产渲染历史。
5. 所有输出在持久化和推送前统一脱敏。

## 权限矩阵

| 操作 | Owner | Admin | Member |
|---|---:|---:|---:|
| 查看项目资源 | ✓ | ✓ | ✓ |
| 编辑环境/需求/接口/场景 | ✓ | ✓ | ✓ |
| 确认模块/场景、创建执行 | ✓ | ✓ | ✓ |
| 管理成员 | ✓ | ✓ | - |
| 删除项目/转移 Owner | ✓ | - | - |

服务层始终先验证项目成员，再按资源 `project_id` 查询；禁止先按资源 ID 查询后补权限。
