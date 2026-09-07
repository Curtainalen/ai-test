import { DeleteOutlined } from '@ant-design/icons'
import { Button, Empty, Form, Input, Modal, Popconfirm, Space, Switch, Table, Typography, message } from 'antd'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useSession } from '../store'

export function EnvironmentsPage() {
  const projectId = useSession((s) => s.projectId)
  const [rows, setRows] = useState<any[]>([])
  const [open, setOpen] = useState(false)
  const load = async () => { if (projectId) setRows(await api<any[]>({ url: `/projects/${projectId}/environments` })) }
  useEffect(() => { void load() }, [projectId])
  if (!projectId) return <Empty description="请先选择项目" />
  const create = async (values: any) => { try { await api({ method: 'post', url: `/projects/${projectId}/environments`, data: { ...values, variables: {}, global_headers: {}, secret_refs: {} } }); setOpen(false); await load() } catch (error) { message.error((error as Error).message) } }
  const remove = async (id: string) => { try { await api({ method: 'delete', url: `/projects/${projectId}/environments/${id}` }); await load(); message.success('测试环境已删除') } catch (error) { message.error((error as Error).message) } }
  return <Space direction="vertical" className="page-block"><Space className="page-title"><div><Typography.Title level={3}>测试环境</Typography.Title><Typography.Text type="secondary">Base URL 是正式执行目标边界</Typography.Text></div><Button type="primary" onClick={() => setOpen(true)}>添加环境</Button></Space><Table rowKey="id" dataSource={rows} columns={[{ title: '名称', dataIndex: 'name' }, { title: 'Base URL', dataIndex: 'base_url' }, { title: '启用', dataIndex: 'is_enabled', render: Boolean }, { title: 'Revision', dataIndex: 'revision' }, { title: '操作', render: (_: unknown, row: any) => <Popconfirm title="确认删除测试环境？" onConfirm={() => void remove(row.id)}><Button type="text" danger icon={<DeleteOutlined />} aria-label={`删除环境 ${row.name}`} /></Popconfirm> }]} /><Modal open={open} title="添加环境" footer={null} onCancel={() => setOpen(false)}><Form layout="vertical" initialValues={{ is_enabled: true }} onFinish={create}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="base_url" label="Base URL" rules={[{ required: true }, { type: 'url' }]}><Input /></Form.Item><Form.Item name="is_enabled" label="启用" valuePropName="checked"><Switch /></Form.Item><Button type="primary" htmlType="submit">保存</Button></Form></Modal></Space>
}
