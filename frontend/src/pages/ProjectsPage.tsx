import { ArrowRightOutlined, DeleteOutlined } from '@ant-design/icons'
import { Button, Empty, Form, Input, Modal, Popconfirm, Space, Table, Typography, message } from 'antd'
import { useEffect, useState } from 'react'

import { api } from '../api'
import { Project, useSession } from '../store'

type ProjectsPageProps = {
  onOpenProject?: () => void
}

export function ProjectsPage({ onOpenProject }: ProjectsPageProps) {
  const { projects, projectId, setProjects, selectProject } = useSession()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    try {
      setProjects(await api<Project[]>({ url: '/projects' }))
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  useEffect(() => { void load() }, [])

  const enterProject = (id: string) => {
    selectProject(id)
    onOpenProject?.()
  }

  const remove = async (id: string) => {
    try { await api({ method: 'delete', url: `/projects/${id}` }); if (projectId === id) selectProject(undefined); await load(); message.success('项目已删除') }
    catch (error) { message.error((error as Error).message) }
  }

  const create = async (values: { name: string; description?: string }) => {
    setSaving(true)
    try {
      const created = await api<Project>({ method: 'post', url: '/projects', data: values })
      await load()
      setOpen(false)
      enterProject(created.id)
      message.success('项目已创建')
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Space direction="vertical" size="large" className="page-block">
      <Space className="page-title">
        <div>
          <Typography.Title level={3}>项目</Typography.Title>
          <Typography.Text type="secondary">选择项目进入工作区，所有资源按项目隔离</Typography.Text>
        </div>
        <Button type="primary" onClick={() => setOpen(true)}>创建项目</Button>
      </Space>
      {projects.length ? (
        <Table<Project>
          rowKey="id"
          dataSource={projects}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          onRow={(project) => ({
            className: project.id === projectId ? 'project-row-selected' : undefined,
            tabIndex: 0,
            role: 'button',
            'aria-label': `进入项目 ${project.name}`,
            onClick: () => enterProject(project.id),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                enterProject(project.id)
              }
            },
          })}
          columns={[
            { title: '项目名称', dataIndex: 'name', render: (value: string) => <Typography.Text strong>{value}</Typography.Text> },
            { title: '描述', dataIndex: 'description', render: (value: string) => value || '暂无描述', ellipsis: true },
            { title: '角色', dataIndex: 'role', width: 120 },
            { title: '操作', width: 180, render: (_: unknown, project: Project) => <Space><Button type="link" icon={<ArrowRightOutlined />} onClick={(event) => { event.stopPropagation(); enterProject(project.id) }}>进入项目</Button><Popconfirm title="确认删除整个项目及其数据？" onConfirm={() => void remove(project.id)}><Button type="text" danger icon={<DeleteOutlined />} aria-label={`删除项目 ${project.name}`} onClick={(event) => event.stopPropagation()} /></Popconfirm></Space> },
          ]}
        />
      ) : <Empty description="暂无项目" />}
      <Modal open={open} title="创建项目" footer={null} onCancel={() => setOpen(false)} destroyOnClose>
        <Form layout="vertical" onFinish={create} clearOnDestroy>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea /></Form.Item>
          <Button type="primary" htmlType="submit" loading={saving}>保存并进入</Button>
        </Form>
      </Modal>
    </Space>
  )
}
