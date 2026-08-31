import { DeleteOutlined, DownOutlined, HolderOutlined, PlusOutlined, ReloadOutlined, RobotOutlined, UpOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Collapse, Empty, Form, Input, InputNumber, Modal, Select, Space, Steps, Table, Tag, Typography, message } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'
import { HttpMethodTag } from './HttpMethodTag'
import type { ApiInterfaceAsset, TestEnvironmentOption } from './RequestComposer'

type Props = { interfaces: ApiInterfaceAsset[]; environments: TestEnvironmentOption[] }
type RequirementModuleOption = { id: string; name: string; status: string; description?: string }
type RequirementTestPointOption = { id: string; stable_key: string; title: string; risk: string }
type ApiScenarioCandidate = {
  id: string
  interface_ids: string[]
  requirement_test_point_ids: string[]
  instruction: string
  content: { proposal?: { name: string; description: string; priority: string; requirement_test_point_ids: string[]; steps: Array<{ seq: number; name: string; interface_id: string; expected_result: string; assertions: AssertionRule[] }> } }
  status: string
  revision: number
  error_message?: string
  confirmed_asset_id?: string
}
type ExtractRule = { name: string; type: 'jmespath'; expression: string; scope: 'scenario'; sensitive: boolean }
type AssertionType = 'status_code' | 'header' | 'json_field' | 'text_contains'
type AssertionRule = { type: AssertionType; expected: unknown; field?: string }
type BodyType = 'none' | 'json' | 'raw' | 'urlencoded' | 'form-data' | 'binary'
type ScenarioStepDraft = {
  seq: number
  name: string
  interface_id: string
  request_override: Record<string, unknown>
  preconditions: unknown[]
  extracts: ExtractRule[]
  assertions: AssertionRule[]
  expected_result: string
  timeout_ms: number
  retry_count: number
  continue_on_failure: boolean
}

type RequestOverride = {
  params?: Record<string, unknown>
  headers?: Record<string, unknown>
  cookies?: Record<string, unknown>
  body_type?: BodyType
  body?: unknown
}
type JsonField = { key: string; value: string }

const assertionLabels: Record<Exclude<AssertionType, 'status_code'>, string> = {
  header: '响应 Header',
  json_field: 'JSON 字段',
  text_contains: '响应文本包含',
}

const jsonValue = (value: unknown, fallback: unknown = {}) => JSON.stringify(value ?? fallback, null, 2)

function parseJson(value: string, label: string) {
  try { return JSON.parse(value || '{}') } catch { throw new Error(`${label} 必须是有效 JSON`) }
}

function requestOverrideFor(step: ScenarioStepDraft): RequestOverride {
  return step.request_override as RequestOverride
}

function jsonFields(value: unknown): JsonField[] {
  if (!value || Array.isArray(value) || typeof value !== 'object') return []
  return Object.entries(value as Record<string, unknown>).map(([key, item]) => ({ key, value: typeof item === 'string' ? item : JSON.stringify(item) }))
}

function jsonFieldsToObject(fields: JsonField[]) {
  return fields.reduce<Record<string, unknown>>((output, field) => {
    if (!field.key.trim()) return output
    try { output[field.key.trim()] = JSON.parse(field.value) } catch { output[field.key.trim()] = field.value }
    return output
  }, {})
}

export function createScenarioStep(interfaceAsset: ApiInterfaceAsset, seq: number): ScenarioStepDraft {
  return {
    seq,
    name: interfaceAsset.summary || `${interfaceAsset.method} ${interfaceAsset.path}`,
    interface_id: interfaceAsset.id,
    request_override: {},
    preconditions: [],
    extracts: [],
    assertions: [{ type: 'status_code', expected: 200 }],
    expected_result: '接口返回 HTTP 200',
    timeout_ms: 30000,
    retry_count: 0,
    continue_on_failure: false,
  }
}

export function normalizeScenarioSteps(steps: ScenarioStepDraft[]) {
  return steps.map((step, index) => ({ ...step, seq: index + 1 }))
}

export function moveScenarioStep(steps: ScenarioStepDraft[], from: number, to: number) {
  if (from < 0 || to < 0 || from >= steps.length || to >= steps.length || from === to) return normalizeScenarioSteps(steps)
  const next = [...steps]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return normalizeScenarioSteps(next)
}

function expectedStatus(step: ScenarioStepDraft) {
  const assertion = step.assertions.find((item) => item.type === 'status_code')
  return typeof assertion?.expected === 'number' ? assertion.expected : 200
}

function withExpectedStatus(step: ScenarioStepDraft, expected: number): ScenarioStepDraft {
  return { ...step, assertions: [{ type: 'status_code', expected }, ...step.assertions.filter((item) => item.type !== 'status_code')] }
}

function displayExpected(value: unknown) {
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function parseExpected(value: string, type: Exclude<AssertionType, 'status_code'>) {
  if (type !== 'json_field') return value
  try { return JSON.parse(value) } catch { return value }
}

export function ScenarioWorkspace({ interfaces, environments }: Props) {
  const projectId = useSession((state) => state.projectId)
  const [scenarios, setScenarios] = useState<any[]>([])
  const [requirementModules, setRequirementModules] = useState<RequirementModuleOption[]>([])
  const [requirementTestPoints, setRequirementTestPoints] = useState<RequirementTestPointOption[]>([])
  const [apiCandidates, setApiCandidates] = useState<ApiScenarioCandidate[]>([])
  const [aiOpen, setAiOpen] = useState(false)
  const [candidateDetail, setCandidateDetail] = useState<ApiScenarioCandidate>()
  const [open, setOpen] = useState(false)
  const [selectorOpen, setSelectorOpen] = useState(false)
  const [selectedInterfaceIds, setSelectedInterfaceIds] = useState<React.Key[]>([])
  const [steps, setSteps] = useState<ScenarioStepDraft[]>([])
  const [activeStepIndex, setActiveStepIndex] = useState<number | null>(null)
  const [draggedStepIndex, setDraggedStepIndex] = useState<number | null>(null)
  const [newExtract, setNewExtract] = useState({ name: '', expression: '', sensitive: false })
  const [newAssertion, setNewAssertion] = useState<{ type: Exclude<AssertionType, 'status_code'>; field: string; expected: string }>({ type: 'json_field', field: '', expected: '' })
  const [requestPreview, setRequestPreview] = useState<any>()
  const [previewing, setPreviewing] = useState(false)
  const [previewEnvironmentId, setPreviewEnvironmentId] = useState<string>()
  const [requestDraft, setRequestDraft] = useState({ params: '{}', headers: '{}', cookies: '{}', body: '' })
  const [jsonBodyFields, setJsonBodyFields] = useState<JsonField[]>([])
  const [execution, setExecution] = useState<any>()
  const [form] = Form.useForm()
  const [aiForm] = Form.useForm()
  const socket = useRef<WebSocket>()

  const load = async () => {
    if (!projectId) return
    const [nextScenarios, modules, candidates, testPoints] = await Promise.all([
      api<any[]>({ url: `/projects/${projectId}/scenarios` }),
      api<RequirementModuleOption[]>({ url: `/projects/${projectId}/requirement-modules`, params: { status: 'confirmed' } }),
      api<{ items: ApiScenarioCandidate[] }>({ url: `/projects/${projectId}/ai/api-scenario-candidates`, params: { page: 1, page_size: 20 } }),
      api<{ items: RequirementTestPointOption[] }>({ url: `/projects/${projectId}/ai/requirement-test-points`, params: { page: 1, page_size: 100 } }),
    ])
    setScenarios(nextScenarios)
    setRequirementModules(Array.isArray(modules) ? modules : [])
    setApiCandidates(Array.isArray(candidates?.items) ? candidates.items : [])
    setRequirementTestPoints(Array.isArray(testPoints?.items) ? testPoints.items : [])
  }

  useEffect(() => {
    void load().catch((error: Error) => message.error(error.message))
    return () => socket.current?.close()
  }, [projectId])

  const activeStep = activeStepIndex === null ? undefined : steps[activeStepIndex]
  const interfaceById = useMemo(() => new Map(interfaces.map((item) => [item.id, item])), [interfaces])
  const interfacesByTag = useMemo(() => {
    const groups = new Map<string, ApiInterfaceAsset[]>()
    interfaces.forEach((item) => {
      const tag = item.tags?.[0] || '未分类'
      groups.set(tag, [...(groups.get(tag) || []), item])
    })
    return [...groups.entries()]
  }, [interfaces])

  useEffect(() => {
    if (!activeStep) return
    const override = requestOverrideFor(activeStep)
    setRequestDraft({
      params: jsonValue(override.params),
      headers: jsonValue(override.headers),
      cookies: jsonValue(override.cookies),
      body: typeof override.body === 'string' ? override.body : jsonValue(override.body),
    })
    setJsonBodyFields(jsonFields(override.body))
    setRequestPreview(undefined)
  }, [activeStepIndex, activeStep?.request_override])

  if (!projectId) return <Empty description="请先选择项目" />

  const openEditor = () => {
    form.resetFields()
    form.setFieldsValue({ priority: 'P2', requirement_module_ids: [] })
    setSteps([])
    setActiveStepIndex(null)
    setSelectedInterfaceIds([])
    setDraggedStepIndex(null)
    setNewExtract({ name: '', expression: '', sensitive: false })
    setNewAssertion({ type: 'json_field', field: '', expected: '' })
    setRequestPreview(undefined)
    setPreviewEnvironmentId(environments.find((item) => item.is_enabled)?.id)
    setOpen(true)
  }

  const addSelectedInterfaces = () => {
    const selected = selectedInterfaceIds.map((id) => interfaceById.get(String(id))).filter((item): item is ApiInterfaceAsset => Boolean(item))
    if (!selected.length) {
      message.warning('请至少选择一个接口')
      return
    }
    setSteps((current) => normalizeScenarioSteps([...current, ...selected.map((item, index) => createScenarioStep(item, current.length + index + 1))]))
    setActiveStepIndex(steps.length)
    setSelectorOpen(false)
    setSelectedInterfaceIds([])
  }

  const updateStep = (index: number, patch: Partial<ScenarioStepDraft>) => {
    setRequestPreview(undefined)
    setSteps((current) => current.map((step, currentIndex) => currentIndex === index ? { ...step, ...patch } : step))
  }

  const updateRequestOverride = (index: number, patch: RequestOverride) => {
    const current = steps[index]
    if (!current) return
    updateStep(index, { request_override: { ...current.request_override, ...patch } })
  }

  const previewStepRequest = async () => {
    if (activeStepIndex === null || !activeStep) return
    const environment = environments.find((item) => item.id === previewEnvironmentId && item.is_enabled)
    if (!environment) {
      message.warning('请先创建并启用一个测试环境')
      return
    }
    setPreviewing(true)
    try {
      const data = await api<{ request_preview: Record<string, unknown>; valid: boolean }>({
        method: 'post',
        url: `/projects/${projectId}/requests/preview`,
        data: { environment_id: environment.id, interface_id: activeStep.interface_id, request_override: activeRequestOverride() },
      })
      setRequestPreview(data.request_preview)
    } catch (error) {
      setRequestPreview(undefined)
      message.error((error as Error).message)
    } finally {
      setPreviewing(false)
    }
  }

  const setBodyType = (bodyType: BodyType | 'inherit') => {
    if (activeStepIndex === null || !activeStep) return
    const next = { ...activeStep.request_override } as RequestOverride
    if (bodyType === 'inherit') {
      delete next.body_type
      delete next.body
    } else {
      next.body_type = bodyType
      if (bodyType === 'json') {
        try { next.body = parseJson(requestDraft.body, 'JSON Body') } catch { next.body = {} }
      } else if (next.body === undefined) next.body = ''
    }
    updateStep(activeStepIndex, { request_override: next })
  }

  const saveRequestMap = (field: 'params' | 'headers' | 'cookies', value: string, label: string) => {
    if (activeStepIndex === null) return
    try { updateRequestOverride(activeStepIndex, { [field]: parseJson(value, label) }) }
    catch (error) { message.error((error as Error).message) }
  }

  const saveBody = (value: string) => {
    if (activeStepIndex === null || !activeStep) return
    const bodyType = requestOverrideFor(activeStep).body_type
    if (!bodyType) return
    try { updateRequestOverride(activeStepIndex, { body: bodyType === 'json' ? parseJson(value, 'JSON Body') : value }) }
    catch (error) { message.error((error as Error).message) }
  }

  const saveJsonBodyFields = (fields: JsonField[]) => {
    if (activeStepIndex === null) return
    const body = jsonFieldsToObject(fields)
    setJsonBodyFields(fields)
    setRequestDraft((current) => ({ ...current, body: jsonValue(body) }))
    updateRequestOverride(activeStepIndex, { body })
  }

  const activeRequestOverride = (): RequestOverride => {
    if (!activeStep) return {}
    const override = { ...requestOverrideFor(activeStep) }
    override.params = parseJson(requestDraft.params, 'Query 参数')
    override.headers = parseJson(requestDraft.headers, 'Header')
    override.cookies = parseJson(requestDraft.cookies, 'Cookie')
    if (override.body_type) override.body = override.body_type === 'json' ? parseJson(requestDraft.body, 'JSON Body') : requestDraft.body
    return override
  }

  const stepsWithCurrentRequestDraft = () => activeStepIndex === null ? steps : steps.map((step, index) => index === activeStepIndex ? { ...step, request_override: activeRequestOverride() } : step)

  const moveStep = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= steps.length) return
    setSteps(moveScenarioStep(steps, index, target))
    setActiveStepIndex(target)
  }

  const removeStep = (index: number) => {
    setSteps((current) => normalizeScenarioSteps(current.filter((_, currentIndex) => currentIndex !== index)))
    setActiveStepIndex((current) => current === null ? null : current === index ? (steps.length > 1 ? Math.max(0, index - 1) : null) : current > index ? current - 1 : current)
  }

  const addExtract = () => {
    if (activeStepIndex === null || !newExtract.name.trim() || !newExtract.expression.trim()) {
      message.warning('请填写变量名和 JMESPath 表达式')
      return
    }
    const name = newExtract.name.trim()
    const duplicate = steps.some((step) => step.extracts.some((item) => item.name === name))
    if (duplicate) {
      message.warning('变量名不能重复，请使用不同名称')
      return
    }
    updateStep(activeStepIndex, { extracts: [...activeStep!.extracts, { name, type: 'jmespath', expression: newExtract.expression.trim(), scope: 'scenario', sensitive: newExtract.sensitive }] })
    setNewExtract({ name: '', expression: '', sensitive: false })
  }

  const removeExtract = (index: number) => {
    if (activeStepIndex !== null) updateStep(activeStepIndex, { extracts: activeStep!.extracts.filter((_, itemIndex) => itemIndex !== index) })
  }

  const addAssertion = () => {
    if (activeStepIndex === null || !newAssertion.expected.trim() || (newAssertion.type !== 'text_contains' && !newAssertion.field.trim())) {
      message.warning('请补充断言字段和期望值')
      return
    }
    const rule: AssertionRule = {
      type: newAssertion.type,
      expected: parseExpected(newAssertion.expected.trim(), newAssertion.type),
      ...(newAssertion.type === 'text_contains' ? {} : { field: newAssertion.field.trim() }),
    }
    updateStep(activeStepIndex, { assertions: [...activeStep!.assertions, rule] })
    setNewAssertion({ type: 'json_field', field: '', expected: '' })
  }

  const removeAssertion = (index: number) => {
    if (activeStepIndex === null) return
    const statusAssertions = activeStep!.assertions.filter((item) => item.type === 'status_code')
    const additionalAssertions = activeStep!.assertions.filter((item) => item.type !== 'status_code')
    updateStep(activeStepIndex, { assertions: [...statusAssertions, ...additionalAssertions.filter((_, itemIndex) => itemIndex !== index)] })
  }

  const create = async () => {
    try {
      const values = await form.validateFields()
      if (!steps.length) throw new Error('请至少添加一个接口步骤')
      const preparedSteps = stepsWithCurrentRequestDraft()
      if (preparedSteps.some((step) => !step.interface_id || !step.name.trim())) throw new Error('每个步骤必须选择接口并填写名称')
      await api({
        method: 'post',
        url: `/projects/${projectId}/scenarios`,
        data: { name: values.name.trim(), description: values.description?.trim() || '', scenario_type: 'api', priority: values.priority, requirement_module_ids: values.requirement_module_ids || [], steps: normalizeScenarioSteps(preparedSteps) },
      })
      setOpen(false)
      await load()
      message.success('场景草稿已创建')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const confirm = async (scenario: any) => {
    try {
      await api({ method: 'post', url: `/projects/${projectId}/scenarios/${scenario.id}/confirm`, params: { revision: scenario.revision } })
      await load()
      message.success('场景已确认')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const run = async (scenario: any, environmentId: string) => {
    const data: any = await api({ method: 'post', url: `/projects/${projectId}/executions`, headers: { 'Idempotency-Key': crypto.randomUUID() }, data: { scenario_id: scenario.id, environment_id: environmentId } })
    setExecution(data)
    const token = localStorage.getItem('access_token')
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
    socket.current?.close()
    socket.current = new WebSocket(`${scheme}://${location.host}/ws/projects/${projectId}/executions/${data.id}`)
    socket.current.onopen = () => socket.current?.send(JSON.stringify({ type: 'auth', token }))
    socket.current.onmessage = (event) => {
      const payload = JSON.parse(event.data)
      if (payload.type === 'snapshot') setExecution(payload.data)
      else void api({ url: `/projects/${projectId}/executions/${data.id}` }).then(setExecution)
    }
  }

  const createAiCandidate = async () => {
    try {
      const values = await aiForm.validateFields()
      await api({ method: 'post', url: `/projects/${projectId}/ai/api-scenario-candidates`, data: {
        interface_ids: values.interface_ids,
        requirement_test_point_ids: values.requirement_test_point_ids || [],
        instruction: values.instruction.trim(),
      } })
      setAiOpen(false)
      aiForm.resetFields()
      await load()
      message.success('AI 候选已提交生成，完成后需人工审核')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const decideCandidate = async (candidate: ApiScenarioCandidate, decision: 'approved' | 'rejected') => {
    try {
      const updated = await api<ApiScenarioCandidate>({
        method: 'post', url: `/projects/${projectId}/ai/api-scenario-candidates/${candidate.id}/decision`,
        data: { decision, revision: candidate.revision, reason: decision === 'rejected' ? '人工审核拒绝' : '' },
      })
      setCandidateDetail(updated)
      await load()
      message.success(decision === 'approved' ? '候选已批准，仍需物化为场景草稿' : '候选已拒绝')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const materializeCandidate = async (candidate: ApiScenarioCandidate) => {
    try {
      await api({ method: 'post', url: `/projects/${projectId}/ai/api-scenario-candidates/${candidate.id}/materialize`, data: { revision: candidate.revision } })
      setCandidateDetail(undefined)
      await load()
      message.success('已创建场景草稿，人工确认前不可执行')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const cancelCandidate = async (candidate: ApiScenarioCandidate) => {
    try {
      await api({ method: 'post', url: `/projects/${projectId}/ai/api-scenario-candidates/${candidate.id}/cancel` })
      await load()
      message.success('候选生成已取消')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const selectorColumns = [{ title: '接口', key: 'interface', render: (_: unknown, item: ApiInterfaceAsset) => <Space direction="vertical" size={1}><Space size={6}><HttpMethodTag method={item.method} /><Typography.Text code>{item.path}</Typography.Text></Space><Typography.Text type="secondary">{item.summary || '未命名接口'}</Typography.Text></Space> }]
  const additionalAssertions = activeStep?.assertions.filter((item) => item.type !== 'status_code') || []
  const availableVariables = steps.slice(0, activeStepIndex ?? 0).flatMap((step) => step.extracts.map((extract) => ({ value: `\${${extract.name}}`, label: `${extract.name} · 第 ${step.seq} 步` })))

  return <Space direction="vertical" className="page-block" size="large">
    <Space className="page-title"><div><Typography.Title level={4}>场景编排</Typography.Title><Typography.Text type="secondary">从已导入接口选择步骤，保存草稿后人工确认才能执行</Typography.Text></div><Space><Button icon={<RobotOutlined />} disabled={!interfaces.length} onClick={() => { aiForm.resetFields(); setAiOpen(true) }}>生成 AI 候选</Button><Button type="primary" disabled={!interfaces.length} onClick={openEditor}>创建场景</Button></Space></Space>
    {!interfaces.length && <Empty description="请先导入至少一个接口" />}
    <div>
      <Space className="page-title"><Typography.Title level={5}>AI 场景候选</Typography.Title><Button aria-label="刷新 AI 候选" icon={<ReloadOutlined />} onClick={() => void load()} /></Space>
      <Table rowKey="id" size="small" pagination={false} dataSource={apiCandidates} locale={{ emptyText: '暂无 AI 场景候选' }} columns={[
        { title: '生成意图', dataIndex: 'instruction', ellipsis: true },
        { title: '候选场景', render: (_, item) => item.content?.proposal?.name || '-' },
        { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'approved' ? 'green' : value === 'pending_review' ? 'gold' : value === 'failed' || value === 'rejected' ? 'red' : undefined}>{value}</Tag> },
        { title: 'Revision', dataIndex: 'revision' },
        { title: '操作', render: (_, item) => <Space><Button onClick={() => setCandidateDetail(item)}>查看差异</Button>{item.status === 'generating' && <Button danger onClick={() => void cancelCandidate(item)}>取消</Button>}</Space> },
      ]} />
    </div>
    <Table rowKey="id" dataSource={scenarios} columns={[
      { title: '名称', dataIndex: 'name' },
      { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
      { title: '版本', dataIndex: 'version' },
      { title: '步骤', dataIndex: 'steps', render: (value) => value.length },
      { title: '操作', render: (_, scenario) => <Space><Button disabled={scenario.status === 'confirmed'} onClick={() => void confirm(scenario)}>确认</Button><Select placeholder="选择环境执行" style={{ width: 210 }} onChange={(id) => void run(scenario, id)} options={environments.filter((item) => item.is_enabled).map((item) => ({ value: item.id, label: item.name }))} disabled={scenario.status !== 'confirmed'} /></Space> },
    ]} />
    {execution && <Card title={`执行进度 · ${execution.status}`} extra={<Button disabled={!['pending', 'running'].includes(execution.status)} onClick={async () => setExecution(await api({ method: 'post', url: `/projects/${projectId}/executions/${execution.id}/cancel` }))}>取消</Button>}><Steps direction="vertical" items={(execution.steps || []).map((step: any) => ({ title: step.name, description: step.error_message || `${step.duration_ms || 0} ms`, status: step.status === 'passed' ? 'finish' : step.status === 'running' ? 'process' : step.status === 'pending' ? 'wait' : 'error' }))} /></Card>}
    <Modal open={aiOpen} title="生成 API 场景候选" okText="提交生成" onOk={() => void createAiCandidate()} onCancel={() => setAiOpen(false)} destroyOnClose>
      <Alert type="warning" showIcon message="模型结果仅作为候选，不会创建、确认或执行正式场景。" />
      <Form form={aiForm} layout="vertical" preserve={false}>
        <Form.Item name="interface_ids" label="允许引用的接口" rules={[{ required: true, message: '请选择至少一个接口' }]}><Select mode="multiple" showSearch optionFilterProp="label" options={interfaces.map((item) => ({ value: item.id, label: `${item.method} ${item.path} · ${item.summary || '未命名'}` }))} /></Form.Item>
        <Form.Item name="requirement_test_point_ids" label="关联已批准需求测试点"><Select mode="multiple" allowClear showSearch optionFilterProp="label" options={requirementTestPoints.map((item) => ({ value: item.id, label: `${item.title} · ${item.risk}` }))} /></Form.Item>
        <Form.Item name="instruction" label="生成意图" rules={[{ required: true, whitespace: true, message: '请填写生成意图' }]}><Input.TextArea rows={4} maxLength={4000} placeholder="例如：覆盖登录成功、鉴权失败和响应字段校验" /></Form.Item>
      </Form>
    </Modal>
    <Modal width={880} open={Boolean(candidateDetail)} title="AI 候选差异审核" footer={candidateDetail ? <Space><Button onClick={() => setCandidateDetail(undefined)}>关闭</Button>{candidateDetail.status === 'pending_review' && <><Button danger onClick={() => void decideCandidate(candidateDetail, 'rejected')}>拒绝</Button><Button type="primary" onClick={() => void decideCandidate(candidateDetail, 'approved')}>批准候选</Button></>}{candidateDetail.status === 'approved' && <Button type="primary" onClick={() => void materializeCandidate(candidateDetail)}>创建场景草稿</Button>}</Space> : null} onCancel={() => setCandidateDetail(undefined)}>
      {candidateDetail && <Space direction="vertical" className="page-block">
        <Alert type="info" showIcon message={`来源范围：${candidateDetail.interface_ids.length} 个接口，${candidateDetail.requirement_test_point_ids.length} 个需求测试点`} description="批准仅改变候选状态；创建的场景仍为 draft，需在场景列表再次人工确认。" />
        {candidateDetail.error_message && <Alert type="error" message={candidateDetail.error_message} />}
        {candidateDetail.content?.proposal ? <>
          <Typography.Title level={5}>{candidateDetail.content.proposal.name}</Typography.Title>
          <Typography.Paragraph>{candidateDetail.content.proposal.description || '无描述'}</Typography.Paragraph>
          <Table rowKey="seq" size="small" pagination={false} dataSource={candidateDetail.content.proposal.steps} columns={[
            { title: '#', dataIndex: 'seq', width: 56 },
            { title: '候选步骤', dataIndex: 'name' },
            { title: '真实接口来源', dataIndex: 'interface_id', render: (id) => { const item = interfaceById.get(id); return item ? <Space><HttpMethodTag method={item.method} /><Typography.Text code>{item.path}</Typography.Text></Space> : <Tag color="red">接口不在当前资产中</Tag> } },
            { title: '预期', dataIndex: 'expected_result' },
            { title: '断言', dataIndex: 'assertions', render: (items) => items.map((item: AssertionRule, index: number) => <Tag key={index}>{item.type}</Tag>) },
          ]} />
        </> : <Empty description={candidateDetail.status === 'generating' ? '正在生成，请稍后刷新' : '没有可审核的候选内容'} />}
      </Space>}
    </Modal>
    <Modal width={1120} open={open} title="创建接口场景" okText="保存草稿" onOk={() => void create()} onCancel={() => setOpen(false)} destroyOnClose>
      <Form form={form} layout="vertical"><div className="scenario-basic-grid"><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true, message: '请输入场景名称' }]}><Input placeholder="例如：用户登录与查询" /></Form.Item><Form.Item name="priority" label="优先级"><Select options={['P0', 'P1', 'P2', 'P3'].map((value) => ({ value }))} /></Form.Item></div><Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item><Form.Item name="requirement_module_ids" label="关联已确认需求模块"><Select mode="multiple" allowClear showSearch optionFilterProp="label" placeholder={requirementModules.length ? '选择需求模块，可多选' : '当前项目没有已确认需求模块'} options={requirementModules.map((item) => ({ value: item.id, label: item.name, title: item.description }))} /></Form.Item></Form>
      <Alert className="scenario-editor-notice" type="info" showIcon message="接口步骤按列表顺序执行。可拖拽步骤卡片排序，变量与断言均使用现有安全执行能力。" />
      <div className="scenario-editor-grid">
        <Card className="scenario-step-list" size="small" title={`步骤 · ${steps.length}`} extra={<Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setSelectorOpen(true)}>添加接口</Button>}>
          {steps.length ? <div className="scenario-step-scroll">{steps.map((step, index) => {
            const interfaceAsset = interfaceById.get(step.interface_id)
            return <Card key={`${step.interface_id}-${step.seq}-${index}`} size="small" draggable className={`scenario-step-card ${activeStepIndex === index ? 'scenario-step-card-active' : ''} ${draggedStepIndex === index ? 'scenario-step-card-dragging' : ''}`} onClick={() => setActiveStepIndex(index)} onDragStart={(event) => { event.dataTransfer.effectAllowed = 'move'; setDraggedStepIndex(index) }} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (draggedStepIndex !== null) { setSteps(moveScenarioStep(steps, draggedStepIndex, index)); setActiveStepIndex(index) } setDraggedStepIndex(null) }} onDragEnd={() => setDraggedStepIndex(null)}>
              <div className="scenario-step-card-content"><span className="scenario-drag-handle" title="拖拽排序"><HolderOutlined /></span><Tag>{step.seq}</Tag><div><Typography.Text strong>{step.name}</Typography.Text><br /><Space size={6}><HttpMethodTag method={interfaceAsset?.method || 'GET'} /><Typography.Text type="secondary" ellipsis={{ tooltip: interfaceAsset?.path }}>{interfaceAsset?.path || '接口不可用'}</Typography.Text></Space></div></div>
              <Space size={0} onClick={(event) => event.stopPropagation()}><Button aria-label="上移步骤" type="text" icon={<UpOutlined />} disabled={index === 0} onClick={() => moveStep(index, -1)} /><Button aria-label="下移步骤" type="text" icon={<DownOutlined />} disabled={index === steps.length - 1} onClick={() => moveStep(index, 1)} /><Button aria-label="删除步骤" type="text" danger icon={<DeleteOutlined />} onClick={() => removeStep(index)} /></Space>
            </Card>
          })}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="从接口库选择一个或多个接口" />}
        </Card>
        <Card size="small" title="步骤配置">
          {activeStep && activeStepIndex !== null ? <Form layout="vertical">
            <Form.Item label="步骤名称"><Input value={activeStep.name} onChange={(event) => updateStep(activeStepIndex, { name: event.target.value })} /></Form.Item>
            <div className="scenario-step-settings-grid"><Form.Item label="期望 HTTP 状态码"><InputNumber min={100} max={599} value={expectedStatus(activeStep)} onChange={(value) => updateStep(activeStepIndex, withExpectedStatus(activeStep, typeof value === 'number' ? value : 200))} /></Form.Item><Form.Item label="超时（毫秒）"><InputNumber min={100} max={300000} value={activeStep.timeout_ms} onChange={(value) => updateStep(activeStepIndex, { timeout_ms: typeof value === 'number' ? value : 30000 })} /></Form.Item><Form.Item label="重试次数"><InputNumber min={0} max={3} value={activeStep.retry_count} onChange={(value) => updateStep(activeStepIndex, { retry_count: typeof value === 'number' ? value : 0 })} /></Form.Item></div>
            <Form.Item label="预期结果"><Input value={activeStep.expected_result} onChange={(event) => updateStep(activeStepIndex, { expected_result: event.target.value })} /></Form.Item>
            <Checkbox checked={activeStep.continue_on_failure} onChange={(event) => updateStep(activeStepIndex, { continue_on_failure: event.target.checked })}>失败后继续执行后续步骤</Checkbox>
            <Collapse className="scenario-request-collapse" items={[
              { key: 'request', label: '请求配置（接口默认配置 + 本步骤覆盖）', children: <>
                <Alert type="info" showIcon message="支持 ${变量} 与 {{变量}}。未填写字段继承接口调试配置；场景执行会自动继承前序步骤响应 Cookie，显式 Cookie 优先。" />
                <div className="scenario-request-workbench">
                  <div className="scenario-request-sidebar"><Typography.Text strong>当前请求</Typography.Text><Space direction="vertical" size={6}><Space><HttpMethodTag method={interfaceById.get(activeStep.interface_id)?.method || 'GET'} /><Typography.Text code>{interfaceById.get(activeStep.interface_id)?.path}</Typography.Text></Space><Typography.Text type="secondary">Cookie：自动继承前序响应</Typography.Text><Form.Item label="预览环境"><Select aria-label="预览环境" value={previewEnvironmentId} onChange={setPreviewEnvironmentId} placeholder="选择环境" options={environments.filter((item) => item.is_enabled).map((item) => ({ value: item.id, label: `${item.name} · ${item.base_url}` }))} /></Form.Item><Button loading={previewing} onClick={() => void previewStepRequest()}>预览最终请求</Button></Space></div>
                  <div className="scenario-request-editor">
                    <div className="scenario-variable-picker"><Typography.Text type="secondary">可用变量（仅前序步骤）：</Typography.Text>{availableVariables.length ? availableVariables.map((variable) => <Tag key={variable.value} color="blue">{variable.value} · {variable.label}</Tag>) : <Typography.Text type="secondary">暂无前序变量；可先在前序步骤“变量提取”中添加。</Typography.Text>}</div>
                    <div className="scenario-request-grid">
                      {(['params', 'headers', 'cookies'] as const).map((field) => <Form.Item key={field} label={field === 'params' ? 'Query 参数 JSON' : field === 'headers' ? 'Header JSON' : 'Cookie JSON'}><Input.TextArea aria-label={`${field} JSON`} rows={4} value={requestDraft[field]} onChange={(event) => setRequestDraft({ ...requestDraft, [field]: event.target.value })} onBlur={(event) => saveRequestMap(field, event.target.value, field === 'params' ? 'Query 参数' : field === 'headers' ? 'Header' : 'Cookie')} placeholder={field === 'headers' ? '{\n  "Authorization": "Bearer ${access_token}"\n}' : '{\n}'} /></Form.Item>)}
                      <Form.Item label="Body 类型"><Select aria-label="Body 类型" value={requestOverrideFor(activeStep).body_type || 'inherit'} onChange={setBodyType} options={[{ value: 'inherit', label: '继承接口默认配置' }, ...(['none', 'json', 'raw', 'urlencoded', 'form-data', 'binary'] as BodyType[]).map((value) => ({ value, label: value }))]} /></Form.Item>
                    </div>
                    {requestOverrideFor(activeStep).body_type === 'json' && <div className="scenario-json-body"><Space className="scenario-json-body-title"><Typography.Text strong>JSON Body 字段</Typography.Text><Button size="small" icon={<PlusOutlined />} onClick={() => saveJsonBodyFields([...jsonBodyFields, { key: '', value: '' }])}>新增字段</Button></Space>{jsonBodyFields.length ? jsonBodyFields.map((field, index) => <div className="scenario-json-field" key={`${field.key}-${index}`}><Input aria-label={`JSON 字段名 ${index + 1}`} placeholder="字段名" value={field.key} onChange={(event) => saveJsonBodyFields(jsonBodyFields.map((item, itemIndex) => itemIndex === index ? { ...item, key: event.target.value } : item))} /><Input aria-label={`JSON 字段值 ${index + 1}`} placeholder="值；字符串无需引号，数字/true 可自动识别" value={field.value} onChange={(event) => saveJsonBodyFields(jsonBodyFields.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.target.value } : item))} /><Select aria-label={`JSON 字段变量 ${index + 1}`} size="small" value={undefined} placeholder="变量" disabled={!availableVariables.length} options={availableVariables} onChange={(value) => saveJsonBodyFields(jsonBodyFields.map((item, itemIndex) => itemIndex === index ? { ...item, value: `${item.value}${value}` } : item))} /><Button aria-label={`删除 JSON 字段 ${index + 1}`} type="text" danger icon={<DeleteOutlined />} onClick={() => saveJsonBodyFields(jsonBodyFields.filter((_, itemIndex) => itemIndex !== index))} /></div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="新增字段后填写登录账号、密码等请求数据" />}</div>}
                    {requestOverrideFor(activeStep).body_type && requestOverrideFor(activeStep).body_type !== 'none' && <Form.Item label={requestOverrideFor(activeStep).body_type === 'json' ? 'JSON 原始内容（复杂对象/数组时使用）' : 'Body 内容'}><Input.TextArea aria-label="步骤 Body" rows={requestOverrideFor(activeStep).body_type === 'json' ? 5 : 8} value={requestDraft.body} onChange={(event) => setRequestDraft({ ...requestDraft, body: event.target.value })} onBlur={(event) => { saveBody(event.target.value); if (requestOverrideFor(activeStep).body_type === 'json') { try { setJsonBodyFields(jsonFields(parseJson(event.target.value, 'JSON Body'))) } catch { /* JSON 校验由 saveBody 提示 */ } } }} placeholder={requestOverrideFor(activeStep).body_type === 'json' ? '{\n  "userAccount": "${userAccount}",\n  "userPassword": "${userPassword}"\n}' : '请求体内容'} /></Form.Item>}
                  </div>
                </div>
                {requestPreview && <><Typography.Text strong>脱敏请求预览</Typography.Text><Typography.Paragraph type="secondary">预览不会发出请求，也不会包含运行时自动继承的 Cookie。</Typography.Paragraph><pre className="scenario-preview-panel">{JSON.stringify(requestPreview, null, 2)}</pre></>}
              </> },
            ]} />
            <Collapse className="scenario-rule-collapse" items={[
              { key: 'extracts', label: `变量提取 (${activeStep.extracts.length})`, children: <><div className="scenario-rule-form"><Input placeholder="变量名，例如 access_token" value={newExtract.name} onChange={(event) => setNewExtract({ ...newExtract, name: event.target.value })} /><Input placeholder="JMESPath，例如 data.access_token" value={newExtract.expression} onChange={(event) => setNewExtract({ ...newExtract, expression: event.target.value })} /><Checkbox checked={newExtract.sensitive} onChange={(event) => setNewExtract({ ...newExtract, sensitive: event.target.checked })}>敏感</Checkbox><Button icon={<PlusOutlined />} onClick={addExtract}>添加</Button></div>{activeStep.extracts.length > 0 && <Table size="small" pagination={false} rowKey="name" dataSource={activeStep.extracts} columns={[{ title: '变量', dataIndex: 'name' }, { title: 'JMESPath', dataIndex: 'expression' }, { title: '敏感', dataIndex: 'sensitive', render: (value) => value ? <Tag color="orange">是</Tag> : '否' }, { title: '操作', render: (_, __, index) => <Button type="link" danger onClick={() => removeExtract(index)}>删除</Button> }]} />}</> },
              { key: 'assertions', label: `附加断言 (${additionalAssertions.length})`, children: <><div className="scenario-rule-form scenario-assertion-form"><Select value={newAssertion.type} options={Object.entries(assertionLabels).map(([value, label]) => ({ value, label }))} onChange={(type) => setNewAssertion({ ...newAssertion, type })} />{newAssertion.type !== 'text_contains' && <Input placeholder={newAssertion.type === 'header' ? 'Header 名，例如 content-type' : 'JSON 字段，例如 data.code'} value={newAssertion.field} onChange={(event) => setNewAssertion({ ...newAssertion, field: event.target.value })} />}<Input placeholder={newAssertion.type === 'json_field' ? '期望值，例如 0、true 或 ok' : '期望值'} value={newAssertion.expected} onChange={(event) => setNewAssertion({ ...newAssertion, expected: event.target.value })} /><Button icon={<PlusOutlined />} onClick={addAssertion}>添加</Button></div>{additionalAssertions.length > 0 && <Table size="small" pagination={false} rowKey={(_, index) => String(index)} dataSource={additionalAssertions} columns={[{ title: '类型', dataIndex: 'type', render: (value) => assertionLabels[value as Exclude<AssertionType, 'status_code'>] }, { title: '字段', dataIndex: 'field', render: (value) => value || '-' }, { title: '期望值', dataIndex: 'expected', render: displayExpected }, { title: '操作', render: (_, __, index) => <Button type="link" danger onClick={() => removeAssertion(index)}>删除</Button> }]} />}</> },
            ]} />
          </Form> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择左侧步骤进行配置" />}
        </Card>
      </div>
    </Modal>
    <Modal width={920} open={selectorOpen} title="选择接口步骤" okText={`添加已选接口 (${selectedInterfaceIds.length})`} onOk={addSelectedInterfaces} onCancel={() => setSelectorOpen(false)} destroyOnClose><Typography.Paragraph type="secondary">按接口标签分组。勾选框支持当前分组全选，可一次添加多个接口。</Typography.Paragraph><Collapse items={interfacesByTag.map(([tag, tagInterfaces]) => ({ key: tag, label: <Space><Typography.Text strong>{tag}</Typography.Text><Tag>{tagInterfaces.length}</Tag></Space>, children: <Table rowKey="id" size="small" pagination={false} dataSource={tagInterfaces} columns={selectorColumns} rowSelection={{ selectedRowKeys: selectedInterfaceIds, preserveSelectedRowKeys: true, onChange: (keys) => setSelectedInterfaceIds(keys) }} /> }))} defaultActiveKey={interfacesByTag.map(([tag]) => tag)} /></Modal>
  </Space>
}
