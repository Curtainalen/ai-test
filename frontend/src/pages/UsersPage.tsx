import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Empty, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'

type ManagedUser = {
  id: string; username: string; name: string; email: string; system_role: 'admin' | 'user'; is_active: boolean
  last_login_at?: string | null; created_at?: string | null
}

type UserForm = {
  username?: string; name?: string; email?: string; system_role: 'admin' | 'user'; is_active?: boolean; password?: string
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'
}

export function UsersPage() {
  const actor = useSession((state) => state.user)
  const [rows, setRows] = useState<ManagedUser[]>([])
  const [editing, setEditing] = useState<ManagedUser>()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<UserForm>()

  const load = async () => setRows(await api<ManagedUser[]>({ url: '/auth/users' }))
  useEffect(() => { if (actor?.system_role === 'admin') void load().catch((error: Error) => message.error(error.message)) }, [actor?.system_role])

  if (actor?.system_role !== 'admin') return <Empty description="仅系统管理员可访问用户管理" />

  const openCreate = () => {
    setEditing(undefined)
    form.resetFields()
    form.setFieldsValue({ system_role: 'user', is_active: true })
    setOpen(true)
  }
  const openEdit = (row: ManagedUser) => {
    setEditing(row)
    form.resetFields()
    form.setFieldsValue({ name: row.name, email: row.email, system_role: row.system_role, is_active: row.is_active })
    setOpen(true)
  }
  const save = async () => {
    try {
      setSaving(true)
      const values = await form.validateFields()
      if (editing) {
        const payload = { name: values.name, email: values.email, system_role: values.system_role, is_active: values.is_active, ...(values.password ? { password: values.password } : {}) }
        await api<ManagedUser>({ method: 'patch', url: `/auth/users/${editing.id}`, data: payload })
      } else {
        await api<ManagedUser>({ method: 'post', url: '/auth/users', data: values })
      }
      setOpen(false)
      await load()
      message.success(editing ? '用户已更新' : '用户已创建')
    } catch (error) { message.error((error as Error).message) } finally { setSaving(false) }
  }
  const toggleActive = async (row: ManagedUser, is_active: boolean) => {
    try {
      await api<ManagedUser>({ method: 'patch', url: `/auth/users/${row.id}`, data: { is_active } })
      await load()
      message.success(is_active ? '用户已启用' : '用户已停用')
    } catch (error) { message.error((error as Error).message) }
  }

  return <Space direction="vertical" size="large" className="page-block">
    <Space className="page-title"><div><Typography.Title level={3}>用户管理</Typography.Title><Typography.Text type="secondary">用户为不可删除资产，可通过停用控制登录权限。</Typography.Text></div><Button aria-label="新增用户" type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增用户</Button></Space>
    <Table rowKey="id" dataSource={rows} locale={{ emptyText: '暂无用户' }} columns={[
      { title: '用户名', dataIndex: 'username' },
      { title: '姓名', dataIndex: 'name', render: (value) => value || '-' },
      { title: '邮箱', dataIndex: 'email', render: (value) => value || '-' },
      { title: '角色', dataIndex: 'system_role', render: (value) => <Tag color={value === 'admin' ? 'blue' : 'default'}>{value === 'admin' ? '管理员' : '普通用户'}</Tag> },
      { title: '状态', render: (_, row: ManagedUser) => <Popconfirm title={row.is_active ? '确认停用该用户？' : '确认启用该用户？'} onConfirm={() => void toggleActive(row, !row.is_active)} disabled={row.id === actor.id}><Switch aria-label={`${row.username} 状态`} checked={row.is_active} checkedChildren="启用" unCheckedChildren="停用" disabled={row.id === actor.id} /></Popconfirm> },
      { title: '最近登录时间', dataIndex: 'last_login_at', render: formatTime },
      { title: '操作', render: (_, row: ManagedUser) => <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>编辑</Button> },
    ]} />
    <Modal open={open} title={editing ? `编辑用户：${editing.username}` : '新增用户'} onCancel={() => setOpen(false)} onOk={() => void save()} okText="保存" confirmLoading={saving} destroyOnClose>
      <Form form={form} layout="vertical">
        {!editing && <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }, { min: 3, max: 64, message: '用户名长度为 3-64 位' }, { pattern: /^[A-Za-z0-9_.-]+$/, message: '仅支持字母、数字、下划线、点和连字符' }]}><Input autoComplete="off" /></Form.Item>}
        <Form.Item name="name" label="姓名" rules={[{ max: 64, message: '姓名最多 64 个字符' }]}><Input /></Form.Item>
        <Form.Item name="email" label="邮箱" rules={[{ max: 255, message: '邮箱最多 255 个字符' }]}><Input /></Form.Item>
        <Form.Item name="system_role" label="系统角色" rules={[{ required: true }]}><Select options={[{ value: 'admin', label: '管理员' }, { value: 'user', label: '普通用户' }]} /></Form.Item>
        {editing && <Form.Item name="is_active" label="启用状态" valuePropName="checked"><Switch disabled={editing.id === actor.id} /></Form.Item>}
        <Form.Item name="password" label={editing ? '重置密码（可选）' : '密码'} rules={[{ required: !editing, message: '请输入密码' }, { min: 10, max: 128, message: '密码长度为 10-128 位' }]}><Input.Password autoComplete="new-password" /></Form.Item>
      </Form>
    </Modal>
  </Space>
}
