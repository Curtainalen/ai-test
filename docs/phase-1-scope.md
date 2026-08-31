# 一期范围冻结

## 目标闭环

创建项目 → 配置环境 → 上传并异步解析需求 → 确认需求模块 → 导入 OpenAPI/Swagger → 单接口 Preview/Run → 编排并确认接口场景 → RQ 异步执行 → WebSocket 查看状态 → 查看不可变脱敏报告。

## 一期包含

- JWT 登录；Owner/Admin/Member 项目角色和项目级资源隔离。
- 项目环境、变量、全局 Header、密钥引用。
- PDF、DOCX、Markdown、TXT 上传；SHA-256 去重；不可变文档版本；异步解析；ContentBlock 来源定位；需求模块人工编辑与确认。
- OpenAPI 3.0/3.1、Swagger 2.0 JSON/YAML 文件导入；远程导入使用白名单与 SSRF 防护；差异预览后确认。
- 共享 RequestComposer：`${var}` 主语法、`{{var}}` 兼容、鉴权、Body、提取、断言、超时、统一脱敏。
- 场景候选、人工确认、revision 乐观锁、有序步骤和显式变量传递。
- RQ 顺序执行、协作取消、幂等提交、步骤事实、WebSocket 快照恢复。
- 不可变报告、步骤证据、错误分类、筛选和需求覆盖状态。

## 一期不包含

- 完整 UI 探索/执行、截图/Trace/DOM 回归；仅保留 `actuator/README.md` 和后续协议边界。
- RAG、Embedding、向量数据库、经验隐式召回。
- Postman/HAR、移动端、套件、定时任务、环境矩阵、复杂 SQL 校验和动态 Python Hook。
- MCP 产品层、自由 Agent 写入、生产环境自主写操作、多协议 LLM 管理平台。
- 完整 OCR 引擎。低质量内容标记为待人工校正；DOC 明确提示转 DOCX/PDF。

## 冻结假设

- 原始文件一期使用受控本地卷保存，数据库只保存相对对象键；后续可替换对象存储。
- 单文件默认上限 20 MiB、PDF 200 页、DOCX 图片 200 张、解析任务 120 秒；均由环境变量配置。
- 远程 OpenAPI 默认关闭；启用时必须配置允许域名列表。
- 一期不保存明文平台密钥；环境配置只保存 `secret://name` 引用，由部署环境注入 `AITEST_SECRET_<NAME>`。
- Worker 对已开始的非幂等步骤不做自动重放；异常恢复将任务归类为执行器异常并保留已完成事实。

## 远程仓库阻塞

2026-08-31 匿名 GitHub API 对 `Curtainalen/ai-test` 返回 404，GitHub CLI 未认证，无法判断仓库不存在还是私有，也无法读取默认分支和保护规则。本地按全新仓库初始化；远程可访问后再核对并推送。
