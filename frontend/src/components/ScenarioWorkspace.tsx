import { Button, Card, Empty, Form, Input, Modal, Select, Space, Steps, Table, Tag, Typography, message } from 'antd'
import { useEffect, useRef, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'
import type { ApiInterfaceAsset, TestEnvironmentOption } from './RequestComposer'

type Props = { interfaces: ApiInterfaceAsset[]; environments: TestEnvironmentOption[] }

export function ScenarioWorkspace({ interfaces, environments }: Props) {
  const projectId = useSession((state) => state.projectId)
  const [scenarios, setScenarios] = useState<any[]>([])
  const [open, setOpen] = useState(false)
  const [execution, setExecution] = useState<any>()
  const socket = useRef<WebSocket>()

  const load = async () => {
    if (projectId) setScenarios(await api<any[]>({ url: `/projects/${projectId}/scenarios` }))
  }

  useEffect(() => {
    void load()
    return () => socket.current?.close()
  }, [projectId])

  if (!projectId) return <Empty description="请先选择项目" />

  const create = async (values: any) => {
    try {
      await api({
        method: 'post',
        url: `/projects/${projectId}/scenarios`,
        data: {
          name: values.name,
          description: values.description || '',
          scenario_type: 'api',
          priority: values.priority,
          requirement_module_ids: (values.requirement_module_ids || '').split(',').map((item: string) => item.trim()).filter(Boolean),
          steps: JSON.parse(values.steps_json),
        },
      })
      setOpen(false)
      await load()
      message.success('场景草稿已创建')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const confirm = async (scenario: any) => {
    await api({ method: 'post', url: `/projects/${projectId}/scenarios/${scenario.id}/confirm`, params: { revision: scenario.revision } })
    await load()
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

  const defaultSteps = JSON.stringify([
    { seq: 1, name: '登录', interface_id: interfaces[0]?.id || null, request_override: {}, preconditions: [], extracts: [{ name: 'access_token', type: 'jmespath', expression: 'data.access_token', scope: 'scenario', sensitive: true }], assertions: [{ type: 'status_code', expected: 200 }], expected_result: '登录成功', timeout_ms: 30000, retry_count: 0, continue_on_failure: false },
    { seq: 2, name: '鉴权请求', interface_id: interfaces[1]?.id || interfaces[0]?.id || null, request_override: { headers: { Authorization: 'Bearer ${access_token}' } }, preconditions: [], extracts: [], assertions: [{ type: 'status_code', expected: 200 }], expected_result: '鉴权成功', timeout_ms: 30000, retry_count: 0, continue_on_failure: false },
  ], null, 2)

  return <Space direction="vertical" className="page-block" size="large">
    <Space className="page-title">
      <div><Typography.Title level={4}>场景编排</Typography.Title><Typography.Text type="secondary">场景必须人工确认后才能创建正式执行任务</Typography.Text></div>
      <Button type="primary" disabled={!interfaces.length} onClick={() => setOpen(true)}>创建场景</Button>
    </Space>
    {!interfaces.length && <Empty description="请先导入至少一个接口" />}
    <Table rowKey="id" dataSource={scenarios} columns={[
      { title: '名称', dataIndex: 'name' },
      { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
      { title: '版本', dataIndex: 'version' },
      { title: '步骤', dataIndex: 'steps', render: (value) => value.length },
      { title: '操作', render: (_, scenario) => <Space><Button disabled={scenario.status === 'confirmed'} onClick={() => void confirm(scenario)}>确认</Button><Select placeholder="选择环境执行" style={{ width: 210 }} onChange={(id) => void run(scenario, id)} options={environments.filter((item) => item.is_enabled).map((item) => ({ value: item.id, label: item.name }))} disabled={scenario.status !== 'confirmed'} /></Space> },
    ]} />
    {execution && <Card title={`执行进度 · ${execution.status}`} extra={<Button disabled={!['pending', 'running'].includes(execution.status)} onClick={async () => setExecution(await api({ method: 'post', url: `/projects/${projectId}/executions/${execution.id}/cancel` }))}>取消</Button>}><Steps direction="vertical" items={(execution.steps || []).map((step: any) => ({ title: step.name, description: step.error_message || `${step.duration_ms || 0} ms`, status: step.status === 'passed' ? 'finish' : step.status === 'running' ? 'process' : step.status === 'pending' ? 'wait' : 'error' }))} /></Card>}
    <Modal width={760} open={open} title="创建接口场景" footer={null} onCancel={() => setOpen(false)}>
      <Form layout="vertical" onFinish={create} initialValues={{ priority: 'P2', steps_json: defaultSteps }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="description" label="描述"><Input.TextArea /></Form.Item>
        <Form.Item name="priority" label="优先级"><Select options={['P0', 'P1', 'P2', 'P3'].map((value) => ({ value }))} /></Form.Item>
        <Form.Item name="requirement_module_ids" label="已确认需求模块 ID（逗号分隔）"><Input /></Form.Item>
        <Form.Item name="steps_json" label="候选步骤 JSON" rules={[{ required: true }]}><Input.TextArea rows={18} /></Form.Item>
        <Button type="primary" htmlType="submit">保存草稿</Button>
      </Form>
    </Modal>
  </Space>
}
