import { CheckCircleOutlined, CloudServerOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, AutoComplete, Button, Collapse, Empty, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { useEffect, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'

type ModelConfig = {
  id: string; name: string; provider: string; protocol: string; model_name: string; base_url?: string | null
  api_key_configured: boolean; api_key_hint: string; extra_params: Record<string, unknown>; timeout_seconds: number
  max_retries: number; context_window?: number | null; supports_vision: boolean; supports_streaming: boolean
  is_default: boolean; is_enabled: boolean; revision: number
}
type ProbeResult = { ok: boolean; latency_ms: number; model: string; error_class?: string | null; upstream_status?: number; upstream_summary?: string; structured_output_mode?: string }

const presets = [
  { value: 'openai', label: 'OpenAI', protocol: 'openai_chat', base_url: 'https://api.openai.com/v1' },
  { value: 'deepseek', label: 'DeepSeek', protocol: 'openai_chat', base_url: 'https://api.deepseek.com/v1' },
  { value: 'anthropic', label: 'Anthropic', protocol: 'anthropic', base_url: 'https://api.anthropic.com/v1' },
  { value: 'gemini', label: 'Google Gemini', protocol: 'gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta' },
  { value: 'ollama', label: 'Ollama', protocol: 'openai_chat', base_url: 'http://localhost:11434/v1' },
  { value: 'custom', label: '自定义兼容端点', protocol: 'openai_chat', base_url: '' },
]
const protocolOptions = [
  { value: 'openai_chat', label: 'OpenAI Chat 兼容' },
  { value: 'anthropic', label: 'Anthropic Messages' },
  { value: 'gemini', label: 'Gemini GenerateContent' },
]
const probeMessages: Record<string, string> = {
  AUTH_FAILED: '认证失败：请检查 API Key、模型权限和服务端配置。',
  NOT_FOUND: '未找到：请检查 Base URL、协议和模型名称。',
  RATE_LIMITED: '请求受限：请稍后重试或检查服务商配额。',
  TIMEOUT: '连接超时：请检查网络、Base URL 或适当增大超时时间。',
  NETWORK: '网络异常：无法连接到模型服务。',
  UPSTREAM_ERROR: '模型服务异常：上游服务返回了服务器错误。',
  UNKNOWN: '连接失败：请检查协议、配置和服务商状态。',
}

function probeMessage(probe: ProbeResult) {
  if (probe.error_class === 'AUTH_FAILED' && probe.upstream_status === 401) return '未授权（HTTP 401）：API Key 缺失、无效或已过期。'
  if (probe.error_class === 'AUTH_FAILED' && probe.upstream_status === 403) return '无权限（HTTP 403）：API Key 已被识别，但没有该模型或接口的调用权限。'
  return probeMessages[probe.error_class || 'UNKNOWN']
}

function probeSummary(probe: ProbeResult) {
  if (probe.ok) return `连接成功，耗时 ${probe.latency_ms} ms（模型：${probe.model}）`
  return `${probeMessage(probe)} ${probe.upstream_summary || ''} 错误分类：${probe.error_class || 'UNKNOWN'}${probe.upstream_status ? ` · HTTP ${probe.upstream_status}` : ''}`
}

function parseExtraParams(value?: string) {
  try { return JSON.parse(value || '{}') } catch { throw new Error('额外参数必须是有效 JSON') }
}

function formPayload(values: Record<string, unknown>) {
  const extra = parseExtraParams(String(values.extra_params || '{}'))
  if (values.structured_output_mode) extra.structured_output_mode = values.structured_output_mode
  const { structured_output_mode: _mode, ...rest } = values
  return { ...rest, base_url: values.base_url || null, extra_params: extra }
}

export function ModelSettingsPage() {
  const user = useSession((state) => state.user)
  const [rows, setRows] = useState<ModelConfig[]>([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ModelConfig>()
  const [saving, setSaving] = useState(false)
  const [probe, setProbe] = useState<ProbeResult>()
  const [structuredProbe, setStructuredProbe] = useState<ProbeResult>()
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [form] = Form.useForm()

  const load = async () => setRows(await api<ModelConfig[]>({ url: '/settings/model-configs' }))
  useEffect(() => { if (user?.system_role === 'admin') void load().catch((error: Error) => message.error(error.message)) }, [user?.system_role])

  if (user?.system_role !== 'admin') return <Empty description="仅系统管理员可访问模型设置" />

  const openCreate = () => {
    setEditing(undefined); setProbe(undefined); setStructuredProbe(undefined); setAvailableModels([])
    form.resetFields()
    form.setFieldsValue({ provider: 'openai', protocol: 'openai_chat', base_url: 'https://api.openai.com/v1', timeout_seconds: 120, max_retries: 0, supports_streaming: true, supports_vision: false, is_enabled: true, structured_output_mode: 'json_object', extra_params: '{}' })
    setOpen(true)
  }
  const openEdit = (row: ModelConfig) => {
    setEditing(row); setProbe(undefined); setStructuredProbe(undefined); setAvailableModels([])
    form.resetFields()
    form.setFieldsValue({ ...row, structured_output_mode: row.extra_params?.structured_output_mode || 'json_object', extra_params: JSON.stringify(row.extra_params || {}, null, 2), api_key: undefined })
    setOpen(true)
  }
  const changePreset = (provider: string) => {
    const preset = presets.find((item) => item.value === provider)
    if (preset) form.setFieldsValue({ protocol: preset.protocol, base_url: preset.base_url })
  }
  const testConnection = async () => {
    try {
      const values = await form.validateFields()
      const result = editing && !values.api_key
        ? await api<ProbeResult>({ method: 'post', url: `/settings/model-configs/${editing.id}/test-connection` })
        : await api<ProbeResult>({ method: 'post', url: '/settings/model-configs/test-connection', data: formPayload(values) })
      setProbe(result)
    } catch (error) { message.error((error as Error).message) }
  }
  const testSaved = async (row: ModelConfig) => {
    try {
      const result = await api<ProbeResult>({ method: 'post', url: `/settings/model-configs/${row.id}/test-connection` })
      if (result.ok) message.success(probeSummary(result))
      else message.error(probeSummary(result), 6)
    } catch (error) { message.error((error as Error).message) }
  }
  const testStructured = async () => {
    try {
      const values = await form.validateFields()
      const result = editing && !values.api_key
        ? await api<ProbeResult>({ method: 'post', url: `/settings/model-configs/${editing.id}/test-structured-output` })
        : await api<ProbeResult>({ method: 'post', url: '/settings/model-configs/test-structured-output', data: formPayload(values) })
      setStructuredProbe(result)
    } catch (error) { message.error((error as Error).message) }
  }
  const fetchModels = async (row: ModelConfig) => {
    try {
      setLoadingModels(true)
      const result = await api<{ items: string[]; message?: string }>({ method: 'get', url: `/settings/model-configs/${row.id}/models` })
      setAvailableModels(result.items)
      if (result.items.length) message.success(`已获取 ${result.items.length} 个模型`)
      else message.info(result.message || '未获取到模型列表')
    } catch (error) { message.error((error as Error).message) } finally { setLoadingModels(false) }
  }
  const save = async () => {
    try {
      setSaving(true)
      const values = await form.validateFields()
      const payload = formPayload(values)
      if (editing) {
        const updated = await api<ModelConfig>({ method: 'patch', url: `/settings/model-configs/${editing.id}`, data: { ...payload, revision: editing.revision } })
        setEditing(updated)
      } else {
        const created = await api<ModelConfig>({ method: 'post', url: '/settings/model-configs', data: payload })
        setEditing(created)
      }
      await load(); message.success('模型配置已保存')
    } catch (error) { message.error((error as Error).message) } finally { setSaving(false) }
  }
  const setDefault = async (row: ModelConfig) => {
    try { await api({ method: 'post', url: `/settings/model-configs/${row.id}/set-default`, data: { revision: row.revision } }); await load(); message.success('默认模型已更新') }
    catch (error) { message.error((error as Error).message) }
  }

  return <Space direction="vertical" className="page-block" size="large">
    <Space className="page-title"><div><Typography.Title level={3}>模型设置</Typography.Title><Typography.Text type="secondary">配置模型连接参数，并在保存前验证连接和结构化输出能力。</Typography.Text></div><Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增模型配置</Button></Space>
    <Table rowKey="id" dataSource={rows} locale={{ emptyText: '暂无模型配置' }} columns={[
      { title: '名称', dataIndex: 'name', render: (value, row: ModelConfig) => <Space>{row.is_default && <Tag color="blue">默认</Tag>}<Typography.Text strong>{value}</Typography.Text></Space> },
      { title: '协议', dataIndex: 'protocol', render: (value) => <Tag>{value}</Tag> },
      { title: '模型', dataIndex: 'model_name' },
      { title: 'Base URL', dataIndex: 'base_url', ellipsis: true, render: (value) => value || '服务商默认' },
      { title: '密钥', render: (_, row: ModelConfig) => row.api_key_configured ? <Tag color="green">已配置 {row.api_key_hint}</Tag> : <Tag>未配置</Tag> },
      { title: '状态', render: (_, row: ModelConfig) => row.is_enabled ? <Tag color="green">启用</Tag> : <Tag color="default">停用</Tag> },
      { title: '操作', render: (_, row: ModelConfig) => <Space wrap><Button size="small" icon={<CloudServerOutlined />} onClick={() => void testSaved(row)}>测试连接</Button><Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>编辑</Button>{!row.is_default && <Popconfirm title="设为全局默认模型？" onConfirm={() => void setDefault(row)}><Button size="small" disabled={!row.is_enabled}>设为默认</Button></Popconfirm>}</Space> },
    ]} />
    <Modal open={open} width={760} title={editing ? '编辑模型配置' : '新增模型配置'} okText="保存" confirmLoading={saving} onOk={() => void save()} onCancel={() => setOpen(false)} destroyOnClose>
      <Form form={form} layout="vertical">
        <div className="model-settings-grid"><Form.Item label="配置名称" name="name" rules={[{ required: true, whitespace: true, max: 64 }]}><Input /></Form.Item><Form.Item label="供应商预设" name="provider" rules={[{ required: true }]}><Select options={presets.map(({ value, label }) => ({ value, label }))} onChange={changePreset} /></Form.Item></div>
        <div className="model-settings-grid"><Form.Item label="协议" name="protocol" rules={[{ required: true }]}><Select options={protocolOptions} /></Form.Item><Form.Item label="模型名称" required><Space.Compact style={{ width: '100%' }}><Form.Item name="model_name" noStyle rules={[{ required: true, whitespace: true, max: 256 }]}><AutoComplete options={availableModels.map((model) => ({ value: model }))} placeholder="可手动输入，或先获取模型" style={{ flex: 1 }} /></Form.Item><Button loading={loadingModels} disabled={!editing} onClick={() => editing && void fetchModels(editing)}>获取模型</Button></Space.Compact></Form.Item></div>
        <Form.Item label="Base URL" name="base_url" rules={[{ type: 'url', message: '请输入有效的 http(s) URL' }]}><Input placeholder="留空使用协议默认地址" /></Form.Item>
        <Form.Item label="API Key" name="api_key" extra={editing?.api_key_configured ? <Typography.Text type="secondary">当前已配置：<Tag color="green">{editing.api_key_hint}</Tag>；输入新 Key 才会替换，留空保持现有密钥。</Typography.Text> : '密钥只显示前后部分字符，保存后不会回显完整内容。'}><Input.Password autoComplete="new-password" placeholder={editing?.api_key_configured ? `已配置 ${editing.api_key_hint}，留空表示保留` : '请输入服务商 API Key'} /></Form.Item>
        <Collapse items={[{ key: 'advanced', label: '高级设置', children: <><div className="model-settings-grid"><Form.Item label="超时（秒）" name="timeout_seconds" rules={[{ required: true }]}><InputNumber min={1} max={300} style={{ width: '100%' }} /></Form.Item><Form.Item label="最大重试次数" name="max_retries" rules={[{ required: true }]}><InputNumber min={0} max={5} style={{ width: '100%' }} /></Form.Item></div><div className="model-settings-grid"><Form.Item label="上下文窗口" name="context_window"><InputNumber min={128} max={2000000} style={{ width: '100%' }} /></Form.Item><Form.Item label="结构化输出模式" name="structured_output_mode"><Select options={[{ value: 'json_object', label: 'JSON Object' }, { value: 'json_schema', label: 'JSON Schema（严格约束）' }]} /></Form.Item></div><Form.Item label="额外参数 JSON" name="extra_params"><Input.TextArea rows={3} /></Form.Item><Space size="large"><Form.Item label="支持视觉" name="supports_vision" valuePropName="checked"><Switch /></Form.Item><Form.Item label="支持流式" name="supports_streaming" valuePropName="checked"><Switch /></Form.Item><Form.Item label="启用配置" name="is_enabled" valuePropName="checked"><Switch /></Form.Item></Space></> }]} />
        <Space style={{ marginTop: 16 }} wrap><Button onClick={() => void testConnection()}>测试临时配置</Button><Button onClick={() => void testStructured()}>测试结构化输出</Button><Typography.Text type="secondary">结构化测试会自动发送固定 JSON 请求，无需手动填写测试内容。</Typography.Text>{probe && <Alert type={probe.ok ? 'success' : 'error'} showIcon icon={probe.ok ? <CheckCircleOutlined /> : undefined} message={probe.ok ? `连接成功，耗时 ${probe.latency_ms} ms` : probeMessage(probe)} description={probe.ok ? `模型：${probe.model}` : `${probe.upstream_summary || ''} 错误分类：${probe.error_class || 'UNKNOWN'}${probe.upstream_status ? ` · HTTP ${probe.upstream_status}` : ''}`} />}{structuredProbe && <Alert type={structuredProbe.ok ? 'success' : 'error'} showIcon message={structuredProbe.ok ? `结构化输出成功（${structuredProbe.structured_output_mode || 'json_object'}）` : `结构化输出失败：${structuredProbe.upstream_summary || structuredProbe.error_class || 'UNKNOWN'}`} />}</Space>
      </Form>
    </Modal>
  </Space>
}
