# WebSocket 协议

路径：`/ws/projects/{project_id}/executions/{execution_id}`。

客户端连接后 5 秒内发送：

```json
{"type":"auth","token":"JWT"}
```

服务端先发送完整 `snapshot`，再发送 `execution_update` 和 `step_update`。每个业务事件含递增 `version`。客户端发现版本不连续或断线后应重连，以新快照恢复。心跳为文本 `ping`/`pong`。
