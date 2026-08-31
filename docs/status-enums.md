# 一期状态枚举

| 对象 | 枚举 |
|---|---|
| 项目 | `active`, `archived` |
| 文档解析 | `pending`, `running`, `completed`, `failed`, `canceled` |
| 需求模块 | `pending_confirmation`, `confirmed`, `changed`, `needs_review` |
| OpenAPI 导入 | `pending_confirmation`, `applied`, `failed`, `canceled` |
| 场景 | `draft`, `pending_confirmation`, `confirmed`, `disabled`, `needs_review` |
| 执行任务 | `pending`, `running`, `completed`, `failed`, `canceled` |
| 执行步骤 | `pending`, `running`, `passed`, `failed`, `error`, `skipped`, `canceled` |
| 报告 | `passed`, `failed`, `error`, `canceled` |
| 需求覆盖 | `unplanned`, `pending_confirmation`, `covered`, `passed`, `failed`, `needs_review` |
| 错误分类 | `request_failed`, `environment_error`, `authentication_failed`, `variable_missing`, `assertion_failed`, `timeout`, `executor_error` |

状态迁移由 service 层集中校验。终态不可回到运行态；报告只在执行进入终态时创建一次。
