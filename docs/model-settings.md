# 全局大模型设置（首期）

## 设计

`model_configs` 是系统级表：名称唯一；`created_by` 关联用户；`revision` 用于乐观锁。`api_key_encrypted` 仅存 Fernet 密文，读取模型只提供 `api_key_configured` 与不可逆提示符。`is_default = true` 由 PostgreSQL 部分唯一索引保护；服务层在一个事务中获取 advisory lock、清除其他默认项并设置目标项。

应用启动要求 `SECRET_KEY` 至少 32 字符。`app.security` 将其 SHA-256 摘要编码为 Fernet key。丢失或更换该值会使既有密文无法解密，服务只返回 `SECRET_DECRYPTION_FAILED`，不会返回密文、明文或底层异常。

服务端仅接受 `openai_chat`、`anthropic`、`gemini`。`provider` 是界面预设，不能改变服务端协议校验。Azure、Bedrock、OpenAI Responses 尚未启用。

## 最小探测报文

```json
// openai_chat: POST {base_url}/chat/completions
{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ping"}],"max_tokens":1,"stream":false}
```

```json
// anthropic: POST {base_url}/messages
{"model":"claude-3-5-haiku-latest","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}
```

```json
// gemini: POST {base_url}/models/{model}:generateContent
{"contents":[{"role":"user","parts":[{"text":"ping"}]}],"generationConfig":{"maxOutputTokens":1}}
```

三种协议分别将 key 放进 `Authorization`、`x-api-key`、`x-goog-api-key` 请求头。探测使用配置自己的超时，不跟随重定向，不读取或返回上游响应体；失败只返回安全的 HTTP 状态摘要和分类。

## API

- `GET /api/settings/model-configs`
- `POST /api/settings/model-configs`
- `PATCH /api/settings/model-configs/{id}`
- `POST /api/settings/model-configs/{id}/set-default`
- `POST /api/settings/model-configs/test-connection`
- `POST /api/settings/model-configs/{id}/test-connection`

所有接口均要求 `system_role == "admin"`。错误分类为 `AUTH_FAILED`、`NOT_FOUND`、`RATE_LIMITED`、`TIMEOUT`、`NETWORK`、`UPSTREAM_ERROR`、`UNKNOWN`。

探测失败时同时返回上游 HTTP 状态（仅状态码，不返回响应正文）：

- `AUTH_FAILED · HTTP 401`：未授权，API Key 缺失、无效或已过期。
- `AUTH_FAILED · HTTP 403`：已识别身份但无模型/接口权限。
- `NOT_FOUND · HTTP 404`：Base URL、协议路径或模型名称不存在。
- `RATE_LIMITED · HTTP 429`：服务商限流或配额不足。
- `UPSTREAM_ERROR · HTTP 5xx`：模型服务端异常。
- `TIMEOUT`：超过配置的连接总超时。
- `NETWORK`：无法建立网络连接或发生网络请求错误。

API Key 在编辑页面只显示前后字符的掩码；输入框保持空值表示“保留现有密钥”，不会把掩码当作新密钥提交。

## 部署

在本地 `.env` 中配置一个随机、独立且至少 32 字符的 `SECRET_KEY`，并妥善备份。不要把它写入仓库、日志或聊天记录。配置后运行 `docker compose up -d --build`，后端会执行 `0004_model_configs` 迁移。
