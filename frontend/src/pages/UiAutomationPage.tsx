import { CheckCircleOutlined, DatabaseOutlined, DeleteOutlined, EditOutlined, EyeOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined, RobotOutlined, SafetyCertificateOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Collapse, Descriptions, Drawer, Empty, Form, Input, InputNumber, Modal, Popconfirm, Progress, Result, Select, Space, Steps, Table, Tabs, Tag, Typography, message } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'

type Locator = { type: string; value: string; name?: string; exact?: boolean }
type Module = { id: string; name: string; description: string; parent_id?: string; revision: number }
type Page = { id: string; module_id: string; name: string; url: string; description: string; revision: number }
type Element = { id: string; page_id: string; name: string; primary_locator: Locator; fallback_locators: Locator[]; iframe_locator?: Locator; verified: boolean; revision: number }
type PageStep = { id: string; module_id: string; page_id: string; name: string; description: string; revision: number }
type Scenario = { id: string; module_id: string; name: string; description: string; status: string; revision: number; steps?: unknown[]; created_at?: string }
type Verification = { id: string; status: string; match_count?: number; visible?: boolean; actionable?: boolean; actual_url?: string; error_message?: string; created_at: string }
type Environment = { id: string; name: string; is_enabled: boolean }
type ExplorationTurn = { id: string; seq: number; state: string; action_proposal: { operation?: string; reason?: string }; approval_status?: string; error_code?: string; error_message?: string; started_at?: string; finished_at?: string; observation?: Record<string, string> }
type Exploration = { id: string; goal: string; start_url: string; status: string; model_config_id?: string; model_name?: string; model_provider?: string; model_revision?: number; error_code?: string; current_url?: string; error_message?: string; created_at?: string; navigation_timeout_ms?: number; operation_timeout_ms?: number; llm_turn_timeout_ms?: number; last_evidence_ref?: string; turns?: ExplorationTurn[] }
type UiExecution = { id: string; scenario_id: string; environment_id: string; status: string; error_message?: string; created_at?: string; started_at?: string; finished_at?: string }
type ReportStep = { seq: number; name: string; status: string; error_category?: string; error_message?: string; duration_ms: number; evidence_refs: string[] }
type UiReport = { id: string; execution_id: string; status: string; summary: Record<string, unknown>; trace_manifest_ref?: string; started_at?: string; finished_at?: string; created_at?: string; steps?: ReportStep[] }
type Bundle = { module_name: string; pages: Array<{ key: string; name: string; url: string }>; elements: Array<{ key: string; name: string; page_key: string; primary_locator: Locator }>; page_steps: Array<{ key: string; name: string; page_key: string; details: Array<{ operation: string; element_key?: string }> }>; scenario_name: string; scenario_step_keys: string[] }
type Candidate = { id: string; candidate_type: string; status: string; exploration_id?: string; execution_id?: string; content: { proposal?: Bundle; error_code?: string; message?: string }; created_at?: string }
type RequirementReview = { id: string; status: string; test_points?: Array<{ id: string; title: string; stable_key: string }> }
type PageResult<T> = { items: T[]; total: number }
type AssetModal = { kind: 'modules' | 'pages' | 'elements'; row?: Module | Page | Element }
const locatorTypes = ['test_id', 'data_testid', 'id', 'role', 'label', 'placeholder', 'name', 'css', 'xpath']

function statusTag(status: string) {
  const color = status === 'completed' || status === 'confirmed' || status === 'passed' || status === 'approved' ? 'green' : status === 'failed' || status === 'rejected' ? 'red' : status === 'pending' || status === 'generating' || status === 'pending_review' || status === 'waiting_approval' ? 'gold' : 'blue'
  const label: Record<string, string> = { draft: '草稿', pending: '排队中', pending_review: '待审核', approved: '已批准', superseded: '已物化', waiting_approval: '等待危险动作审批', generating: 'AI 生成中', running: '执行中', completed: '完成', failed: '失败', confirmed: '已确认', canceled: '已取消', passed: '通过', rejected: '已驳回' }
  return <Tag color={color}>{label[status] || status}</Tag>
}

const errorLabels: Record<string, string> = {
  BROWSER_LAUNCH_ERROR: '浏览器启动失败', BROWSER_RUNTIME_ERROR: '浏览器运行异常',
  PAGE_NAVIGATION_TIMEOUT: '页面加载超时', PAGE_DNS_ERROR: '域名解析失败',
  PAGE_CONNECTION_REFUSED: '目标服务拒绝连接', PAGE_CERTIFICATE_ERROR: 'HTTPS 证书错误',
  UI_REDIRECT_FORBIDDEN: '跳转地址不在允许范围', UI_PATH_FORBIDDEN: '访问路径不在允许范围',
  ACTUATOR_COMPATIBILITY_ERROR: '执行器与 Playwright 版本不兼容', EXPLORATION_BROWSER_ERROR: '浏览器探索异常',
  BROWSER_OPERATION_TIMEOUT: '浏览器操作超时', UI_EXPLORATION_TIMEOUT: '探索会话总超时',
  LLM_GATEWAY_TIMEOUT: '模型网关超时',
  LLM_AUTH_FAILED: '模型认证失败', LLM_RATE_LIMITED: '模型请求频率受限',
  LLM_NETWORK_ERROR: '模型网络请求失败', LLM_RESPONSE_JSON_INVALID: '模型返回 JSON 格式错误',
  LLM_RESPONSE_SCHEMA_INVALID: '模型返回结构不符合要求', LLM_UPSTREAM_ERROR: '模型服务异常',
}
function errorText(value?: string) {
  if (!value) return '未提供错误详情'
  const code = value.split(':', 1)[0]
  return `${errorLabels[code] || '探索失败'}（${code}）：${value.slice(code.length + 1).trim()}`
}

function jsonLocators(value?: string): Locator[] {
  if (!value?.trim()) return []
  const parsed = JSON.parse(value)
  if (!Array.isArray(parsed)) throw new Error('备用定位器必须是 JSON 数组')
  return parsed
}

export function UiAutomationPage() {
  const projectId = useSession((state) => state.projectId)
  const [modules, setModules] = useState<Module[]>([])
  const [pages, setPages] = useState<Page[]>([])
  const [elements, setElements] = useState<Element[]>([])
  const [pageSteps, setPageSteps] = useState<PageStep[]>([])
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [verifications, setVerifications] = useState<Verification[]>([])
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [explorations, setExplorations] = useState<Exploration[]>([])
  const [executions, setExecutions] = useState<UiExecution[]>([])
  const [reports, setReports] = useState<UiReport[]>([])
  const [reportDetail, setReportDetail] = useState<UiReport>()
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [testPoints, setTestPoints] = useState<Array<{ id: string; title: string; stable_key: string }>>([])
  const [wizardOpen, setWizardOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [assetModal, setAssetModal] = useState<AssetModal>()
  const [activeTab, setActiveTab] = useState('flows')
  const [confirming, setConfirming] = useState<string>()
  const [form] = Form.useForm()
  const [assetForm] = Form.useForm()

  const load = async () => {
    if (!projectId) return
    try {
      const [ms, ps, es, ss, sc, vs, envs, explorationRows, executionRows, reportRows, candidateRows, reviewRows] = await Promise.all([
        api<PageResult<Module>>({ url: `/projects/${projectId}/ui/modules` }), api<PageResult<Page>>({ url: `/projects/${projectId}/ui/pages` }),
        api<PageResult<Element>>({ url: `/projects/${projectId}/ui/elements` }), api<PageResult<PageStep>>({ url: `/projects/${projectId}/ui/page-steps` }),
        api<PageResult<Scenario>>({ url: `/projects/${projectId}/ui/scenarios` }), api<PageResult<Verification>>({ url: `/projects/${projectId}/ui/verifications` }),
        api<Environment[]>({ url: `/projects/${projectId}/environments` }), api<PageResult<Exploration>>({ url: `/projects/${projectId}/ui/explorations` }),
        api<PageResult<UiExecution>>({ url: `/projects/${projectId}/ui/executions` }), api<PageResult<UiReport>>({ url: `/projects/${projectId}/ui/reports` }),
        api<PageResult<Candidate>>({ url: `/projects/${projectId}/ui/candidates` }),
        api<PageResult<RequirementReview>>({ url: `/projects/${projectId}/ai/requirement-reviews` }),
      ])
      const reviewDetails = await Promise.all(reviewRows.items.filter((item) => item.status === 'approved').map((item) => api<RequirementReview>({ url: `/projects/${projectId}/ai/requirement-reviews/${item.id}` })))
      setModules(ms.items); setPages(ps.items); setElements(es.items); setPageSteps(ss.items); setScenarios(sc.items); setVerifications(vs.items)
      const detailedExplorations = await Promise.all(explorationRows.items.map((item) => ['pending', 'running', 'waiting_approval', 'failed'].includes(item.status) ? api<Exploration>({ url: `/projects/${projectId}/ui/explorations/${item.id}` }) : item))
      setEnvironments(envs.filter((item) => item.is_enabled)); setExplorations(detailedExplorations); setExecutions(executionRows.items); setReports(reportRows.items); setCandidates(candidateRows.items)
      setTestPoints(reviewDetails.flatMap((item) => item.test_points || []))
    } catch (error) { message.error((error as Error).message) }
  }

  useEffect(() => { void load() }, [projectId])
  useEffect(() => {
    if (!projectId || !explorations.some((item) => ['pending', 'running', 'waiting_approval'].includes(item.status)) && !candidates.some((item) => item.status === 'generating')) return
    const timer = window.setInterval(() => void load(), 3500)
    return () => window.clearInterval(timer)
  }, [projectId, explorations, candidates])

  const bundleCandidates = useMemo(() => candidates.filter((item) => item.candidate_type === 'automation_bundle'), [candidates])
  const latestCandidate = bundleCandidates[0]
  if (!projectId) return <Empty description="请先选择项目" />

  const openWizard = () => {
    form.setFieldsValue({ environment_id: environments[0]?.id, start_url: '/', allowed_paths: '/', max_steps: 5, total_timeout_ms: 120000, navigation_timeout_ms: 30000, operation_timeout_ms: 8000, llm_turn_timeout_ms: 45000 })
    setWizardOpen(true)
  }
  const createAiTest = async () => {
    try {
      const value = await form.validateFields()
      const exploration = await api<Exploration>({ method: 'post', url: `/projects/${projectId}/ui/explorations`, data: { environment_id: value.environment_id, goal: value.goal, requirement_test_point_ids: value.requirement_test_point_ids || [], start_url: value.start_url, allowed_paths: value.allowed_paths.split('\n').map((item: string) => item.trim()).filter(Boolean), max_steps: value.max_steps, total_timeout_ms: value.total_timeout_ms, navigation_timeout_ms: value.navigation_timeout_ms, operation_timeout_ms: value.operation_timeout_ms, llm_turn_timeout_ms: value.llm_turn_timeout_ms, actions: [] } })
      await api({ method: 'post', url: `/projects/${projectId}/ui/explorations/${exploration.id}/start` })
      setWizardOpen(false); setActiveTab('flows'); message.success('已开始受控探索，完成后将自动生成待确认的测试流程'); await load()
    } catch (error) { message.error((error as Error).message) }
  }
  const reviewCandidate = async (candidate: Candidate, decision: 'approved' | 'rejected') => {
    setConfirming(candidate.id)
    try {
      await api({ method: 'post', url: `/projects/${projectId}/ui/candidates/${candidate.id}/review`, data: { decision } })
      message.success(decision === 'approved' ? '候选已批准，尚未写入正式资产' : '候选已驳回'); await load()
    } catch (error) { message.error((error as Error).message) } finally { setConfirming(undefined) }
  }
  const materializeBundle = async (candidate: Candidate) => {
    setConfirming(candidate.id)
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/candidates/${candidate.id}/confirm-bundle`, data: {} }); message.success('已创建草稿测试流程，请验证 Locator 后确认场景'); await load() }
    catch (error) { message.error((error as Error).message) } finally { setConfirming(undefined) }
  }
  const confirmScenario = async (scenario: Scenario) => {
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/scenarios/${scenario.id}/confirm`, params: { revision: scenario.revision } }); message.success('UI 场景已确认'); await load() }
    catch (error) { message.error((error as Error).message) }
  }
  const decideTurn = async (exploration: Exploration, turn: ExplorationTurn, decision: 'approved' | 'rejected') => {
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/explorations/${exploration.id}/turns/${turn.id}/decision`, data: { decision } }); await load() }
    catch (error) { message.error((error as Error).message) }
  }
  const runScenario = async (scenario: Scenario) => {
    const environmentId = environments[0]?.id
    if (!environmentId) { message.warning('请先配置并启用测试环境'); return }
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/scenarios/${scenario.id}/executions`, headers: { 'Idempotency-Key': `ui-${Date.now()}-${Math.random()}` }, data: { environment_id: environmentId } }); message.success('UI 执行任务已排队'); await load() } catch (error) { message.error((error as Error).message) }
  }
  const cancelExecution = async (execution: UiExecution) => {
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/executions/${execution.id}/cancel` }); await load() } catch (error) { message.error((error as Error).message) }
  }
  const cancelExploration = async (exploration: Exploration) => {
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/explorations/${exploration.id}/cancel` }); await load() } catch (error) { message.error((error as Error).message) }
  }
  const retryExploration = async (exploration: Exploration) => {
    try {
      const created = await api<Exploration>({ method: 'post', url: `/projects/${projectId}/ui/explorations`, data: {
        environment_id: environments[0]?.id, goal: exploration.goal, requirement_test_point_ids: [],
        start_url: exploration.start_url, allowed_paths: ['/'], max_steps: 5, total_timeout_ms: 120000, navigation_timeout_ms: 30000, operation_timeout_ms: 8000, llm_turn_timeout_ms: 45000, actions: [],
      } })
      await api({ method: 'post', url: `/projects/${projectId}/ui/explorations/${created.id}/start` })
      message.success('已创建新的探索会话'); await load()
    } catch (error) { message.error((error as Error).message) }
  }
  const openReport = async (report: UiReport) => {
    try { setReportDetail(await api<UiReport>({ url: `/projects/${projectId}/ui/reports/${report.id}` })) }
    catch (error) { message.error((error as Error).message) }
  }
  const openAsset = (kind: AssetModal['kind'], row?: Module | Page | Element) => {
    setAssetModal({ kind, row })
    assetForm.setFieldsValue(row ? { ...row, primary_type: (row as Element).primary_locator?.type, primary_value: (row as Element).primary_locator?.value, primary_name: (row as Element).primary_locator?.name, fallback_json: JSON.stringify((row as Element).fallback_locators || [], null, 2) } : { primary_type: 'test_id' })
  }
  const saveAsset = async () => {
    if (!assetModal) return
    try {
      const value = await assetForm.validateFields(); const { kind, row } = assetModal
      let data: Record<string, unknown> = value
      if (kind === 'elements') data = { page_id: value.page_id, name: value.name, description: value.description || '', primary_locator: { type: value.primary_type, value: value.primary_value, name: value.primary_name || undefined }, fallback_locators: jsonLocators(value.fallback_json) }
      const url = `/projects/${projectId}/ui/${kind}${row ? `/${row.id}` : ''}`
      if (row) data.revision = row.revision
      await api({ method: row ? 'patch' : 'post', url, data }); setAssetModal(undefined); message.success('高级资产已保存'); await load()
    } catch (error) { message.error((error as Error).message) }
  }
  const removeAsset = async (kind: AssetModal['kind'], id: string) => {
    try { await api({ method: 'delete', url: `/projects/${projectId}/ui/${kind}/${id}` }); message.success('已删除'); await load() } catch (error) { message.error((error as Error).message) }
  }
  const verify = async (element: Element) => {
    const environmentId = environments[0]?.id
    if (!environmentId) { message.warning('请先配置并启用测试环境'); return }
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/elements/${element.id}/verify`, data: { environment_id: environmentId } }); message.success('定位器验证已提交到 UI actuator'); await load() } catch (error) { message.error((error as Error).message) }
  }
  const cancelVerification = async (verification: Verification) => {
    try { await api({ method: 'post', url: `/projects/${projectId}/ui/verifications/${verification.id}/cancel` }); await load() }
    catch (error) { message.error((error as Error).message) }
  }

  const candidatePreview = latestCandidate?.content.proposal
  const explorationRunning = explorations.find((item) => ['pending', 'running', 'waiting_approval'].includes(item.status))
  const pendingTurn = explorationRunning?.turns?.find((turn) => turn.approval_status === 'pending')
  const testFlow = <Space direction="vertical" size="large" className="page-block">
    {explorationRunning && <Alert type="info" showIcon message="正在受控探索" description={<Space><span>{explorationRunning.goal}</span><Progress size="small" percent={explorationRunning.status === 'running' ? 55 : 20} style={{ width: 150 }} /><Button size="small" danger onClick={() => void cancelExploration(explorationRunning)}>取消探索</Button></Space>} />}
    {explorations.filter((item) => item.status === 'failed').slice(0, 1).map((item) => { const turns = item.turns || []; const turn = turns[turns.length - 1]; return <Alert key={item.id} type="error" showIcon message="受控探索失败" description={<Space direction="vertical"><span>{item.error_code ? `${errorLabels[item.error_code] || item.error_code}：${item.error_message || '无详细信息'}` : errorText(item.error_message)}</span><Typography.Text type="secondary">本次调用模型：{item.model_name || '历史任务未记录'}{item.model_provider ? `（${item.model_provider}）` : ''}{item.model_revision ? `，配置版本 ${item.model_revision}` : ''}</Typography.Text><Typography.Text type="secondary">预算：页面 {item.navigation_timeout_ms || 30000} ms，操作 {item.operation_timeout_ms || 8000} ms，模型单回合 {item.llm_turn_timeout_ms || 45000} ms</Typography.Text>{turn && <Typography.Text type="secondary">最后回合：#{turn.seq} · {turn.state}{turn.error_code ? ` · ${turn.error_code}` : ''}{turn.observation?.screenshot_evidence_ref ? ' · 已保留截图' : ''}{turn.observation?.dom_evidence_ref ? '、DOM' : ''}</Typography.Text>}</Space>} action={<Button onClick={() => void retryExploration(item)}>重新探索</Button>} />})}
    {explorationRunning?.status === 'waiting_approval' && pendingTurn && <Alert type="warning" showIcon message="危险动作等待审批" description={`${pendingTurn.action_proposal.operation || ''}：${pendingTurn.action_proposal.reason || ''}`} action={<Space><Button danger onClick={() => void decideTurn(explorationRunning, pendingTurn, 'rejected')}>拒绝</Button><Button type="primary" onClick={() => void decideTurn(explorationRunning, pendingTurn, 'approved')}>批准本次动作</Button></Space>} />}
    {latestCandidate && <Card title="AI 测试候选" extra={statusTag(latestCandidate.status)}>
      {latestCandidate.status === 'generating' && <Result status="info" title="正在生成测试流程" subTitle="正在根据受控探索中的页面结构生成页面、元素、定位器、步骤和断言候选。" />}
      {latestCandidate.status === 'failed' && <Result status="error" title="候选生成失败" subTitle={latestCandidate.content.message || '未写入任何正式资产'} />}
      {candidatePreview && <Space direction="vertical" size="middle" className="page-block">
        <Descriptions size="small" column={2} items={[{ key: 'module', label: '模块', children: candidatePreview.module_name }, { key: 'scenario', label: '测试流程', children: candidatePreview.scenario_name }, { key: 'pages', label: '页面', children: candidatePreview.pages.length }, { key: 'elements', label: '元素候选', children: candidatePreview.elements.length }, { key: 'steps', label: '执行步骤', children: candidatePreview.scenario_step_keys.length }]} />
        <Collapse size="small" items={[{ key: 'pages', label: `页面与定位器 (${candidatePreview.pages.length} / ${candidatePreview.elements.length})`, children: <Table size="small" rowKey="key" pagination={false} dataSource={candidatePreview.elements} columns={[{ title: '元素', dataIndex: 'name' }, { title: '主定位器', render: (_, row) => `${row.primary_locator.type}: ${row.primary_locator.value}` }, { title: '页面', dataIndex: 'page_key' }]} /> }, { key: 'steps', label: `步骤 (${candidatePreview.page_steps.length})`, children: <Table size="small" rowKey="key" pagination={false} dataSource={candidatePreview.page_steps} columns={[{ title: '步骤', dataIndex: 'name' }, { title: '动作', render: (_, row) => row.details.map((detail) => detail.operation).join(' -> ') }]} /> }]} />
        {latestCandidate.status === 'pending_review' && <Alert showIcon type="warning" message="候选尚未批准，不会写入正式资产" action={<Space><Button danger onClick={() => void reviewCandidate(latestCandidate, 'rejected')}>驳回</Button><Button type="primary" icon={<CheckCircleOutlined />} loading={confirming === latestCandidate.id} onClick={() => void reviewCandidate(latestCandidate, 'approved')}>批准候选</Button></Space>} />}
        {latestCandidate.status === 'approved' && <Alert showIcon type="info" message="候选已批准，创建后仍是不可执行的草稿场景" action={<Button type="primary" loading={confirming === latestCandidate.id} onClick={() => void materializeBundle(latestCandidate)}>创建草稿场景</Button>} />}
      </Space>}
    </Card>}
    <Card title="已确认测试流程" extra={<Button type="primary" icon={<RobotOutlined />} onClick={openWizard}>新建 AI 测试</Button>}>
      <Table rowKey="id" dataSource={scenarios} pagination={{ pageSize: 8 }} locale={{ emptyText: '还没有确认的测试流程。输入测试目标后，系统会生成候选供你确认。' }} columns={[{ title: '名称', dataIndex: 'name' }, { title: '状态', dataIndex: 'status', render: statusTag }, { title: '步骤', render: (_, row) => row.steps?.length ?? '-' }, { title: '创建时间', dataIndex: 'created_at' }, { title: '操作', render: (_, row) => <Space>{row.status === 'draft' && <Button onClick={() => void confirmScenario(row)}>确认场景</Button>}<Button type="primary" icon={<PlayCircleOutlined />} disabled={row.status !== 'confirmed'} onClick={() => void runScenario(row)}>执行</Button></Space> }]} />
    </Card>
  </Space>

  return <Space direction="vertical" className="page-block" size="large">
    <Space className="page-title"><div><Typography.Title level={3}>UI 自动化</Typography.Title><Typography.Text type="secondary">从测试目标生成可审核的浏览器测试流程，确认后再执行。</Typography.Text></div><Space><Button icon={<DatabaseOutlined />} onClick={() => setAdvancedOpen(true)}>高级资产</Button><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button><Button type="primary" icon={<RobotOutlined />} onClick={openWizard}>新建 AI 测试</Button></Space></Space>
    <Steps size="small" current={latestCandidate?.status === 'pending' || latestCandidate?.status === 'pending_review' ? 2 : explorationRunning || explorations.some((item) => item.status === 'failed') ? 1 : 0} items={[{ title: '测试目标' }, { title: '受控探索' }, { title: '审核候选' }, { title: '执行与报告' }]} />
    <Tabs activeKey={activeTab} onChange={setActiveTab} items={[{ key: 'flows', label: '测试流程', children: testFlow }, { key: 'executions', label: '执行记录', children: <Card><Table rowKey="id" dataSource={executions} pagination={{ pageSize: 10 }} locale={{ emptyText: '尚无 UI 执行记录' }} columns={[{ title: '任务', dataIndex: 'id', render: (value) => value.slice(0, 12) }, { title: '状态', dataIndex: 'status', render: statusTag }, { title: '开始时间', dataIndex: 'started_at' }, { title: '错误', dataIndex: 'error_message' }, { title: '操作', render: (_, row) => <Button icon={<StopOutlined />} danger disabled={!['pending', 'running'].includes(row.status)} onClick={() => void cancelExecution(row)}>取消</Button> }]} /></Card> }, { key: 'reports', label: '执行报告', children: <Card><Table rowKey="id" dataSource={reports} pagination={{ pageSize: 10 }} locale={{ emptyText: '尚无 UI 执行报告' }} columns={[{ title: '报告', dataIndex: 'id', render: (value) => value.slice(0, 12) }, { title: '状态', dataIndex: 'status', render: statusTag }, { title: '完成时间', dataIndex: 'finished_at' }, { title: 'Trace', dataIndex: 'trace_manifest_ref', render: (value) => value ? <Tag>受控引用</Tag> : '-' }, { title: '操作', render: (_, row) => <Button icon={<EyeOutlined />} onClick={() => void openReport(row)}>查看</Button> }]} /></Card> }]} />

    <Modal open={wizardOpen} title="新建 AI 测试" width={640} okText="开始 AI 探索" onCancel={() => setWizardOpen(false)} onOk={() => void createAiTest()} destroyOnClose>
      <Form form={form} layout="vertical"><Form.Item name="goal" label="测试目标" rules={[{ required: true, message: '请说明要验证的业务流程和预期结果' }]}><Input.TextArea rows={4} placeholder="例如：验证用户可以登录并进入工作台，错误密码要显示明确提示。" /></Form.Item><Form.Item name="requirement_test_point_ids" label="需求测试点"><Select mode="multiple" allowClear options={testPoints.map((item) => ({ value: item.id, label: `${item.stable_key} · ${item.title}` }))} placeholder="选择已批准评审中的测试点" /></Form.Item><Form.Item name="environment_id" label="测试环境" rules={[{ required: true }]}><Select options={environments.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item><Form.Item name="start_url" label="起始页面" rules={[{ required: true }]}><Input placeholder="/login" /></Form.Item><Collapse ghost items={[{ key: 'scope', label: '范围设置', children: <><Form.Item name="allowed_paths" label="允许访问的路径（每行一个）" rules={[{ required: true }]}><Input.TextArea rows={3} placeholder={'/login\n/dashboard'} /></Form.Item><Space wrap><Form.Item name="max_steps" label="最大探索步数"><InputNumber min={1} max={50} /></Form.Item><Form.Item name="total_timeout_ms" label="总超时（毫秒）"><InputNumber min={1000} max={300000} step={1000} /></Form.Item><Form.Item name="navigation_timeout_ms" label="页面加载超时"><InputNumber min={1000} max={60000} step={1000} /></Form.Item><Form.Item name="operation_timeout_ms" label="浏览器操作超时"><InputNumber min={500} max={30000} step={500} /></Form.Item><Form.Item name="llm_turn_timeout_ms" label="模型单回合超时"><InputNumber min={1000} max={60000} step={1000} /></Form.Item></Space></> }]} /></Form>
    </Modal>

    <Drawer open={advancedOpen} title="高级资产" onClose={() => setAdvancedOpen(false)} size="large" destroyOnClose>
      <Alert type="info" showIcon message="仅在需要细调定位器、排查验证或维护历史资产时使用。常规流程从“新建 AI 测试”开始。" style={{ marginBottom: 16 }} />
      <Tabs items={[{ key: 'modules', label: '模块', children: <Card extra={<Button icon={<PlusOutlined />} onClick={() => openAsset('modules')}>新增</Button>}><Table size="small" rowKey="id" dataSource={modules} pagination={{ pageSize: 5 }} columns={[{ title: '名称', dataIndex: 'name' }, { title: '操作', render: (_, row) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openAsset('modules', row)} /><Popconfirm title="确认删除？" onConfirm={() => void removeAsset('modules', row.id)}><Button type="text" danger icon={<DeleteOutlined />} /></Popconfirm></Space> }]} /></Card> }, { key: 'pages', label: '页面', children: <Card extra={<Button icon={<PlusOutlined />} onClick={() => openAsset('pages')}>新增</Button>}><Table size="small" rowKey="id" dataSource={pages} pagination={{ pageSize: 5 }} columns={[{ title: '名称', dataIndex: 'name' }, { title: 'URL', dataIndex: 'url' }, { title: '操作', render: (_, row) => <Button type="text" icon={<EditOutlined />} onClick={() => openAsset('pages', row)} /> }]} /></Card> }, { key: 'elements', label: '元素与定位器', children: <Card extra={<Button icon={<PlusOutlined />} onClick={() => openAsset('elements')}>新增</Button>}><Table size="small" rowKey="id" dataSource={elements} pagination={{ pageSize: 5 }} columns={[{ title: '元素', dataIndex: 'name' }, { title: '定位器', render: (_, row) => `${row.primary_locator.type}: ${row.primary_locator.value}` }, { title: '验证', render: (_, row) => row.verified ? <Tag color="green">已验证</Tag> : <Tag>未验证</Tag> }, { title: '操作', render: (_, row) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openAsset('elements', row)} /><Button icon={<SafetyCertificateOutlined />} size="small" onClick={() => void verify(row)}>验证</Button></Space> }]} /></Card> }, { key: 'history', label: '验证历史', children: <Table size="small" rowKey="id" dataSource={verifications} pagination={{ pageSize: 6 }} columns={[{ title: '状态', dataIndex: 'status', render: statusTag }, { title: '匹配', dataIndex: 'match_count' }, { title: '可见', dataIndex: 'visible' }, { title: '可操作', dataIndex: 'actionable' }, { title: '实际页面', dataIndex: 'actual_url' }, { title: '错误', dataIndex: 'error_message' }, { title: '操作', render: (_, row) => <Button size="small" danger disabled={!['pending', 'running'].includes(row.status)} onClick={() => void cancelVerification(row)}>取消</Button> }]} /> }]} />
    </Drawer>

    <Drawer open={Boolean(reportDetail)} title="UI 执行报告" onClose={() => setReportDetail(undefined)} size="large" destroyOnClose>
      {reportDetail && <Space direction="vertical" size="middle" className="page-block">
        <Descriptions column={2} size="small" items={[{ key: 'status', label: '状态', children: statusTag(reportDetail.status) }, { key: 'execution', label: '执行任务', children: reportDetail.execution_id }, { key: 'started', label: '开始时间', children: reportDetail.started_at || '-' }, { key: 'finished', label: '完成时间', children: reportDetail.finished_at || '-' }, { key: 'trace', label: 'Trace manifest 引用', children: reportDetail.trace_manifest_ref || '未生成' }]} />
        <Table size="small" rowKey="seq" dataSource={reportDetail.steps || []} pagination={false} columns={[{ title: '#', dataIndex: 'seq', width: 56 }, { title: '步骤', dataIndex: 'name' }, { title: '状态', dataIndex: 'status', render: statusTag }, { title: '失败分类', dataIndex: 'error_category', render: (value) => value || '-' }, { title: '耗时', dataIndex: 'duration_ms', render: (value) => `${value} ms` }, { title: '证据引用', dataIndex: 'evidence_refs', render: (value: string[]) => value?.length ? <Space wrap>{value.map((item) => <Tag key={item}>{item.slice(0, 12)}</Tag>)}</Space> : '-' }, { title: '错误', dataIndex: 'error_message' }]} />
      </Space>}
    </Drawer>

    <Modal open={Boolean(assetModal)} title="编辑高级资产" onCancel={() => setAssetModal(undefined)} onOk={() => void saveAsset()} destroyOnClose width={620}><Form form={assetForm} layout="vertical">{assetModal?.kind === 'pages' && <Form.Item name="module_id" label="模块" rules={[{ required: true }]}><Select options={modules.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>}{assetModal?.kind === 'elements' && <Form.Item name="page_id" label="页面" rules={[{ required: true }]}><Select options={pages.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>}<Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item>{assetModal?.kind === 'pages' && <Form.Item name="url" label="页面 URL 或相对路径" rules={[{ required: true }]}><Input /></Form.Item>}{assetModal?.kind === 'elements' && <><Space.Compact block><Form.Item name="primary_type" label="主定位器类型" rules={[{ required: true }]} style={{ width: '35%' }}><Select options={locatorTypes.map((value) => ({ value }))} /></Form.Item><Form.Item name="primary_value" label="主定位器值" rules={[{ required: true }]} style={{ width: '65%' }}><Input /></Form.Item></Space.Compact><Form.Item name="primary_name" label="Role 名称（可选）"><Input /></Form.Item><Form.Item name="fallback_json" label="备用定位器 JSON"><Input.TextArea rows={4} placeholder={'[{"type":"css","value":"button.login"}]'} /></Form.Item></>}</Form></Modal>
  </Space>
}
