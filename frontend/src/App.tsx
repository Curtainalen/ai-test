import {
  ApiOutlined,
  FileTextOutlined,
  LogoutOutlined,
  ProjectOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Button, Layout, Menu, Select, Space, Typography } from 'antd'
import { useState } from 'react'

import { ApiAssetsPage } from './pages/ApiAssetsPage'
import { EnvironmentsPage } from './pages/EnvironmentsPage'
import { LoginPage } from './pages/LoginPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ReportsPage } from './pages/ReportsPage'
import { RequirementsPage } from './pages/RequirementsPage'
import { useSession } from './store'

const { Header, Sider, Content } = Layout

export default function App() {
  const { user, projects, projectId, selectProject, logout } = useSession()
  const [page, setPage] = useState('projects')

  if (!user) return <LoginPage />

  const pages: Record<string, React.ReactNode> = {
    projects: <ProjectsPage onOpenProject={() => setPage('environments')} />,
    environments: <EnvironmentsPage />,
    requirements: <RequirementsPage />,
    apis: <ApiAssetsPage />,
    reports: <ReportsPage />,
  }

  return (
    <Layout className="app-shell">
      <Header className="topbar">
        <Typography.Title level={3}>AI Test</Typography.Title>
        <Space>
          <Select
            value={projectId}
            placeholder="选择项目"
            style={{ width: 220 }}
            onChange={selectProject}
            options={projects.map((project) => ({ value: project.id, label: project.name }))}
          />
          <span>{user.name || user.username}</span>
          <Button type="text" icon={<LogoutOutlined />} onClick={logout}>退出</Button>
        </Space>
      </Header>
      <Layout>
        <Sider theme="light" width={220}>
          <Menu
            mode="inline"
            selectedKeys={[page]}
            onClick={({ key }) => setPage(key)}
            items={[
              { key: 'projects', icon: <ProjectOutlined />, label: '项目' },
              { key: 'environments', icon: <SettingOutlined />, label: '测试环境' },
              { key: 'requirements', icon: <FileTextOutlined />, label: '需求文档' },
              { key: 'apis', icon: <ApiOutlined />, label: '接口自动化' },
              { key: 'reports', icon: <FileTextOutlined />, label: '执行报告' },
            ]}
          />
        </Sider>
        <Content className="content">{pages[page]}</Content>
      </Layout>
    </Layout>
  )
}
