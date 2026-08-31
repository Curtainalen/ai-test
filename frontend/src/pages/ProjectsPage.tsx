import { ArrowRightOutlined } from '@ant-design/icons'
import { Button, Card, Empty, Form, Input, List, Modal, Space, Typography, message } from 'antd'
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
        <List
          grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 3, xl: 3, xxl: 4 }}
          dataSource={projects}
          renderItem={(project) => (
            <List.Item>
              <Card
                hoverable
                className={project.id === projectId ? 'project-card project-card-selected' : 'project-card'}
                onClick={() => enterProject(project.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    enterProject(project.id)
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`进入项目 ${project.name}`}
                title={project.name}
                extra={project.role}
                actions={[<span key="enter"><ArrowRightOutlined /> 进入项目</span>]}
              >
                {project.description || '暂无描述'}
              </Card>
            </List.Item>
          )}
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
