# UI Actuator

UI actuator 由 Docker Compose 的 `actuator` 服务运行，独立消费 Redis 的
`ui-actuator` 队列，不与 API 场景 worker 或探索会话共享浏览器实例。

执行链路：确认的 UI 场景 -> UI 执行任务快照 -> RQ -> 独立 Chromium
Browser Context -> 步骤状态/证据 -> UI 不可变报告 -> WebSocket。

安全边界：

- 任务、环境、场景、页面、元素和证据始终按 `project_id` 隔离。
- 每个任务创建并在 finally 关闭独立 Playwright、Browser、BrowserContext。
- 网络限制为环境 origin；跳转必须处于场景快照页面范围。
- 只执行结构化的导航、点击、输入、选择、悬停、键盘、等待和断言动作；不执行用户脚本、坐标操作、任意请求头、代理或文件路径。
- 密码输入只允许 `secret://` 引用；当前平台没有 UI 密钥解析器时，任务会以 `UI_SECRET_UNRESOLVED` 终止，绝不回退为明文。
- DOM 和截图在保存前脱敏。Trace 尚不持久化，因为原始 Trace 的渲染数据无法可靠脱敏。
- UI 执行任务具有租约、心跳和协作式取消字段；断线或浏览器异常进入可解释失败状态，不自动重跑。

前端通过 `/ws/projects/{project_id}/ui-executions/{execution_id}` 接收快照和进度事件；认证令牌仍由 WebSocket 首帧传入，不放入 URL。
