import { ImportOutlined, UploadOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Form,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import { useEffect, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'

type ImportMode = 'file' | 'url'
type UrlImportValues = {
  url: string
  auth_type: 'none' | 'basic' | 'bearer' | 'header'
  username?: string
  password?: string
  token?: string
  header_name?: string
  header_value?: string
}

export function ApiAssetsPage() {
  const projectId = useSession((state) => state.projectId)
  const [rows, setRows] = useState<any[]>([])
  const [pending, setPending] = useState<any>()
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [importOpen, setImportOpen] = useState(false)
  const [importMode, setImportMode] = useState<ImportMode>('file')
  const [importFile, setImportFile] = useState<File>()
  const [importing, setImporting] = useState(false)
  const [urlForm] = Form.useForm<UrlImportValues>()
  const authType = Form.useWatch('auth_type', urlForm) || 'none'

  const load = async () => {
    if (projectId) setRows(await api<any[]>({ url: `/projects/${projectId}/interfaces` }))
  }

  useEffect(() => { void load() }, [projectId])

  if (!projectId) return <Empty description="请先选择项目" />

  const openImport = () => {
    setImportMode('file')
    setImportFile(undefined)
    urlForm.resetFields()
    urlForm.setFieldValue('auth_type', 'none')
    setImportOpen(true)
  }

  const runImport = async () => {
    setImporting(true)
    try {
      let data: any
      if (importMode === 'file') {
        if (!importFile) {
          message.warning('请选择 OpenAPI JSON/YAML 文件')
          return
        }
        const form = new FormData()
        form.append('file', importFile)
        data = await api({ method: 'post', url: `/projects/${projectId}/api-imports`, data: form })
      } else {
        const values = await urlForm.validateFields()
        const auth = {
          type: values.auth_type,
          username: values.username,
          password: values.password,
          token: values.token,
          header_name: values.header_name,
          header_value: values.header_value,
        }
        data = await api({
          method: 'post',
          url: `/projects/${projectId}/api-imports/url`,
          data: { url: values.url, auth },
        })
      }
      setPending(data)
      const selectable = [
        ...(data.diff?.added || []),
        ...(data.diff?.modified || []).map((item: any) => item.after),
      ]
      setSelectedKeys(selectable.map((item: any) => item.stable_key))
      setImportOpen(false)
      message.success('已生成导入差异，请确认后入库')
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setImporting(false)
    }
  }

  const confirmImport = async () => {
    await api({
      method: 'post',
      url: `/projects/${projectId}/api-imports/${pending.id}/confirm`,
      params: { revision: pending.revision },
      data: { selected_stable_keys: selectedKeys },
    })
    setPending(undefined)
    setSelectedKeys([])
    await load()
    message.success('接口资产已更新')
  }

  return (
    <Space direction="vertical" className="page-block" size="large">
      <Space className="page-title">
        <div>
          <Typography.Title level={3}>接口资产</Typography.Title>
          <Typography.Text type="secondary">从文件或受控 URL 导入 OpenAPI / Swagger</Typography.Text>
        </div>
        <Button type="primary" icon={<ImportOutlined />} onClick={openImport}>导入</Button>
      </Space>

      {pending && (
        <Alert
          type={pending.diff.conflicts.length ? 'warning' : 'info'}
          showIcon
          message={`待确认导入 · ${pending.source_type === 'url' ? 'URL' : '文件'} · ${pending.source_name}`}
          description={(() => {
            const added = pending.diff.added || []
            const modified = (pending.diff.modified || []).map((item: any) => item.after)
            const selectable = [...added, ...modified]
            const allSelected = selectable.length > 0 && selectedKeys.length === selectable.length
            return (
              <Space direction="vertical" size="middle" className="import-diff-actions">
                <Space wrap>
                  <Tag color="blue">新增 {added.length}</Tag>
                  <Tag color="orange">修改 {modified.length}</Tag>
                  <Tag>删除 {pending.diff.deleted.length}</Tag>
                  <Tag color="red">冲突 {pending.diff.conflicts.length}</Tag>
                </Space>
                {selectable.length > 0 && (
                  <Checkbox
                    checked={allSelected}
                    indeterminate={selectedKeys.length > 0 && !allSelected}
                    onChange={(event) => setSelectedKeys(event.target.checked ? selectable.map((item: any) => item.stable_key) : [])}
                  >
                    全选新增/修改接口（已选 {selectedKeys.length}/{selectable.length}）
                  </Checkbox>
                )}
                {selectable.length > 0 && (
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="stable_key"
                    dataSource={selectable}
                    rowSelection={{
                      selectedRowKeys: selectedKeys,
                      onChange: (keys) => setSelectedKeys(keys as string[]),
                    }}
                    columns={[
                      { title: '变更', key: 'change', render: (_: unknown, item: any) => added.some((entry: any) => entry.stable_key === item.stable_key) ? <Tag color="blue">新增</Tag> : <Tag color="orange">修改</Tag> },
                      { title: '方法', dataIndex: 'method', render: (value: string) => <Tag>{value}</Tag> },
                      { title: '路径', dataIndex: 'path' },
                      { title: '摘要', dataIndex: 'summary' },
                    ]}
                  />
                )}
                {pending.diff.deleted.length > 0 && <Typography.Text type="warning">删除项仅展示，不会在选择性上传时自动删除已有接口。</Typography.Text>}
                <Button
                  type="primary"
                  disabled={pending.diff.conflicts.length > 0 || selectedKeys.length === 0}
                  onClick={() => void confirmImport()}
                >
                  确认上传已选接口
                </Button>
              </Space>
            )
          })()}
        />
      )}

      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: '方法', dataIndex: 'method', render: (value) => <Tag>{value}</Tag> },
          { title: '路径', dataIndex: 'path' },
          { title: '摘要', dataIndex: 'summary' },
          { title: 'Tags', dataIndex: 'tags', render: (value) => value?.join(', ') },
        ]}
      />

      <Modal
        open={importOpen}
        title="导入接口资产"
        okText="生成差异预览"
        cancelText="取消"
        confirmLoading={importing}
        onOk={() => void runImport()}
        onCancel={() => setImportOpen(false)}
        destroyOnClose
        width={680}
      >
        <Space direction="vertical" size="middle" className="import-modal-content">
          <Segmented
            block
            value={importMode}
            onChange={(value) => setImportMode(value as ImportMode)}
            options={[
              { value: 'file', label: '文件导入' },
              { value: 'url', label: 'URL 导入' },
            ]}
          />
          {importMode === 'file' ? (
            <Upload
              accept=".json,.yaml,.yml"
              maxCount={1}
              beforeUpload={(file) => {
                setImportFile(file)
                return false
              }}
              fileList={importFile ? [{ uid: '-1', name: importFile.name, status: 'done' }] : []}
              onRemove={() => {
                setImportFile(undefined)
                return true
              }}
            >
              <Button icon={<UploadOutlined />}>选择 JSON/YAML 文件</Button>
            </Upload>
          ) : (
            <Form form={urlForm} layout="vertical" initialValues={{ auth_type: 'none' }}>
              <Alert
                type="info"
                showIcon
                message="仅允许管理员配置的域名；重定向和解析地址会再次执行安全校验"
              />
              <Form.Item
                name="url"
                label="OpenAPI 文档 URL"
                rules={[
                  { required: true, message: '请输入 OpenAPI 文档 URL' },
                  { type: 'url', message: '请输入完整的 HTTP/HTTPS URL' },
                ]}
              >
                <Input placeholder="https://api.example.com/openapi.json" />
              </Form.Item>
              <Form.Item name="auth_type" label="拉取鉴权">
                <Select options={[
                  { value: 'none', label: '无鉴权' },
                  { value: 'basic', label: 'Basic' },
                  { value: 'bearer', label: 'Bearer' },
                  { value: 'header', label: '自定义 Header' },
                ]} />
              </Form.Item>
              {authType === 'basic' && (
                <Space.Compact block>
                  <Form.Item name="username" label="用户名" rules={[{ required: true }]} style={{ width: '50%' }}>
                    <Input autoComplete="off" />
                  </Form.Item>
                  <Form.Item name="password" label="密码" rules={[{ required: true }]} style={{ width: '50%' }}>
                    <Input.Password autoComplete="new-password" />
                  </Form.Item>
                </Space.Compact>
              )}
              {authType === 'bearer' && (
                <Form.Item name="token" label="Bearer Token" rules={[{ required: true }]}>
                  <Input.Password autoComplete="off" />
                </Form.Item>
              )}
              {authType === 'header' && (
                <Space.Compact block>
                  <Form.Item name="header_name" label="Header 名称" rules={[{ required: true }]} style={{ width: '42%' }}>
                    <Input placeholder="X-API-Key" />
                  </Form.Item>
                  <Form.Item name="header_value" label="Header 值" rules={[{ required: true }]} style={{ width: '58%' }}>
                    <Input.Password autoComplete="off" />
                  </Form.Item>
                </Space.Compact>
              )}
              <Typography.Text type="secondary">鉴权值仅用于本次拉取，不保存到导入记录。</Typography.Text>
            </Form>
          )}
        </Space>
      </Modal>
    </Space>
  )
}
