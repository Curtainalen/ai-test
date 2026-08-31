import { Button, Card, Empty, Form, Input, InputNumber, Select, Space, Tabs, Tag, Typography, message } from 'antd'
import { useEffect, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'

export type ApiInterfaceAsset = {
  id: string
  method: string
  path: string
  summary?: string
  tags?: string[]
  parameters?: Array<{ name?: string; in?: string; example?: unknown; schema?: { example?: unknown; default?: unknown } }>
  request_body?: Record<string, unknown>
  security?: unknown[]
  manual_config?: Record<string, any>
}

export type TestEnvironmentOption = {
  id: string
  name: string
  base_url: string
  is_enabled: boolean
}

type Props = {
  interfaceAsset?: ApiInterfaceAsset | null
  environments: TestEnvironmentOption[]
}

const jsonValue = (value: unknown, fallback: unknown = {}) => JSON.stringify(value ?? fallback, null, 2)

function parameterValues(asset: ApiInterfaceAsset, location: string) {
  return Object.fromEntries(
    (asset.parameters || [])
      .filter((parameter) => parameter.in === location && parameter.name)
      .map((parameter) => [
        parameter.name as string,
        parameter.example ?? parameter.schema?.example ?? parameter.schema?.default ?? '',
      ]),
  )
}

function requestBodyExample(asset: ApiInterfaceAsset) {
  const content = asset.request_body?.content as Record<string, any> | undefined
  const json = content?.['application/json']
  return json?.example ?? json?.examples?.default?.value ?? json?.schema?.example ?? {}
}

function formValues(asset?: ApiInterfaceAsset | null) {
  const manual = asset?.manual_config || {}
  return {
    method: asset?.method || 'GET',
    url: asset?.path || '',
    path_params: jsonValue(manual.path_params ?? (asset ? parameterValues(asset, 'path') : {})),
    params: jsonValue(manual.params ?? (asset ? parameterValues(asset, 'query') : {})),
    headers: jsonValue(manual.headers ?? (asset ? parameterValues(asset, 'header') : {})),
    cookies: jsonValue(manual.cookies ?? (asset ? parameterValues(asset, 'cookie') : {})),
    variables: jsonValue(manual.variables ?? {}),
    body_type: manual.body_type || (asset?.request_body ? 'json' : 'none'),
    body: typeof manual.body === 'string' ? manual.body : jsonValue(manual.body ?? (asset ? requestBodyExample(asset) : {})),
    auth_type: manual.auth?.type || 'none',
    auth_value: manual.auth?.token || manual.auth?.value || '',
    auth_username: manual.auth?.username || '',
    auth_password: manual.auth?.password || '',
    auth_key: manual.auth?.key || 'X-API-Key',
    auth_in: manual.auth?.in || 'header',
    expected_status: manual.assertions?.find((item: any) => item.type === 'status_code')?.expected ?? 200,
  }
}

function parseJson(value: string, label: string) {
  try {
    return JSON.parse(value || '{}')
  } catch {
    throw new Error(`${label} 必须是有效 JSON`)
  }
}

export function RequestComposer({ interfaceAsset, environments }: Props) {
  const projectId = useSession((state) => state.projectId)
  const [result, setResult] = useState<any>()
  const [form] = Form.useForm()
  const authType = Form.useWatch('auth_type', form) || 'none'

  useEffect(() => {
    form.setFieldsValue(formValues(interfaceAsset))
    setResult(undefined)
  }, [form, interfaceAsset])

  if (!projectId) return null
  if (!interfaceAsset) return <Card><Empty description="从左侧选择一个已导入接口开始调试" /></Card>

  const submit = async (run: boolean) => {
    try {
      const values = await form.validateFields()
      const body = values.body_type === 'json' ? parseJson(values.body || '{}', 'JSON Body') : values.body
      const auth = values.auth_type === 'bearer'
        ? { type: 'bearer', token: values.auth_value }
        : values.auth_type === 'basic'
          ? { type: 'basic', username: values.auth_username, password: values.auth_password }
          : values.auth_type === 'api_key'
            ? { type: 'api_key', key: values.auth_key, value: values.auth_value, in: values.auth_in }
            : { type: 'none' }
      const request = {
        method: values.method,
        url: values.url,
        path_params: parseJson(values.path_params, 'Path 参数'),
        params: parseJson(values.params, 'Query 参数'),
        headers: parseJson(values.headers, 'Header'),
        cookies: parseJson(values.cookies, 'Cookie'),
        body_type: values.body_type,
        body,
        auth,
        variables: parseJson(values.variables, '变量'),
        assertions: [{ type: 'status_code', expected: values.expected_status }],
      }
      setResult(await api({
        method: 'post',
        url: `/projects/${projectId}/requests/${run ? 'run' : 'preview'}`,
        data: { environment_id: values.environment_id, interface_id: interfaceAsset.id, request },
      }))
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const enabledEnvironments = environments.filter((environment) => environment.is_enabled)
  return (
    <Card
      className="request-composer"
      title={<Space><span>接口调试</span><Tag>{interfaceAsset.method}</Tag><Typography.Text type="secondary">{interfaceAsset.summary || interfaceAsset.path}</Typography.Text></Space>}
    >
      <Form form={form} layout="vertical">
        <Space wrap className="composer-request-line">
          <Form.Item name="environment_id" label="测试环境" rules={[{ required: true, message: '请选择测试环境' }]}>
            <Select
              placeholder="选择测试环境"
              style={{ width: 260 }}
              options={enabledEnvironments.map((environment) => ({
                value: environment.id,
                label: `${environment.name} · ${environment.base_url}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="method" label="Method"><Select style={{ width: 110 }} options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'].map((value) => ({ value }))} /></Form.Item>
          <Form.Item name="url" label="URL / Path" rules={[{ required: true, message: '请输入 URL 或路径' }]}><Input style={{ width: 360 }} /></Form.Item>
        </Space>
        <Tabs items={[
          {
            key: 'params', label: '参数', children: <div className="composer-json-grid">
              <Form.Item name="path_params" label="Path 参数 JSON"><Input.TextArea rows={6} /></Form.Item>
              <Form.Item name="params" label="Query 参数 JSON"><Input.TextArea rows={6} /></Form.Item>
              <Form.Item name="headers" label="Header JSON"><Input.TextArea rows={6} /></Form.Item>
              <Form.Item name="cookies" label="Cookie JSON"><Input.TextArea rows={6} /></Form.Item>
              <Form.Item name="variables" label="请求变量 JSON"><Input.TextArea rows={6} /></Form.Item>
            </div>,
          },
          {
            key: 'body', label: 'Body', children: <>
              <Form.Item name="body_type" label="类型"><Select style={{ width: 180 }} options={['none', 'json', 'raw', 'urlencoded', 'form-data', 'binary'].map((value) => ({ value }))} /></Form.Item>
              <Form.Item name="body" label="内容"><Input.TextArea rows={9} /></Form.Item>
            </>,
          },
          {
            key: 'auth', label: '鉴权与断言', children: <Space wrap align="start">
              <Form.Item name="auth_type" label="鉴权"><Select style={{ width: 140 }} options={[{ value: 'none', label: '无鉴权' }, { value: 'bearer', label: 'Bearer' }, { value: 'basic', label: 'Basic' }, { value: 'api_key', label: 'API Key' }]} /></Form.Item>
              {authType === 'basic' && <><Form.Item name="auth_username" label="用户名"><Input /></Form.Item><Form.Item name="auth_password" label="密码"><Input.Password autoComplete="off" /></Form.Item></>}
              {authType === 'api_key' && <><Form.Item name="auth_key" label="Key 名称"><Input /></Form.Item><Form.Item name="auth_in" label="位置"><Select style={{ width: 110 }} options={[{ value: 'header', label: 'Header' }, { value: 'query', label: 'Query' }]} /></Form.Item></>}
              {authType !== 'none' && authType !== 'basic' && <Form.Item name="auth_value" label={authType === 'bearer' ? 'Bearer Token/密钥引用' : 'Key 值/密钥引用'}><Input.Password autoComplete="off" /></Form.Item>}
              <Form.Item name="expected_status" label="期望状态码"><InputNumber min={100} max={599} /></Form.Item>
            </Space>,
          },
        ]} />
        <Space>
          <Button onClick={() => void submit(false)}>Preview</Button>
          <Button type="primary" onClick={() => void submit(true)}>运行接口</Button>
        </Space>
      </Form>
      {result && <><Typography.Title level={5}>脱敏结果</Typography.Title><pre className="result-panel">{JSON.stringify(result, null, 2)}</pre></>}
    </Card>
  )
}
