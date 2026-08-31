import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ModelSettingsPage } from './ModelSettingsPage'

const apiMock = vi.fn()
let systemRole = 'admin'

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({
  useSession: (selector: (state: unknown) => unknown) => selector({ user: { id: 'u1', username: 'admin', name: 'Admin', system_role: systemRole } }),
}))

describe('ModelSettingsPage', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    systemRole = 'admin'
    apiMock.mockReset()
    apiMock.mockImplementation(({ url }: { url: string }) => {
      if (url === '/settings/model-configs') return Promise.resolve([{ id: 'model-1', name: '默认模型', provider: 'openai', protocol: 'openai_chat', model_name: 'gpt-test', base_url: null, api_key_configured: true, api_key_hint: 'sk-***ab3f', extra_params: {}, timeout_seconds: 30, max_retries: 0, supports_vision: false, supports_streaming: true, is_default: true, is_enabled: true, revision: 1 }])
      if (url === '/settings/model-configs/test-connection') return Promise.resolve({ ok: true, latency_ms: 18, model: 'gpt-test', error_class: null })
      if (url === '/settings/model-configs/model-1/test-connection') return Promise.resolve({ ok: true, latency_ms: 12, model: 'gpt-test', error_class: null })
      return Promise.resolve({})
    })
  })

  it('renders the admin model configuration table without exposing API keys', async () => {
    render(<ModelSettingsPage />)
    expect(await screen.findByText('默认模型')).toBeInTheDocument()
    expect(screen.getByText('已配置 sk-***ab3f')).toBeInTheDocument()
    expect(screen.queryByText('sk-secret-value')).not.toBeInTheDocument()
  })

  it('shows a connection test result for a temporary configuration', async () => {
    render(<ModelSettingsPage />)
    fireEvent.click(await screen.findByRole('button', { name: /新增模型配置/ }))
    fireEvent.change(screen.getByLabelText('配置名称'), { target: { value: '探测模型' } })
    fireEvent.change(screen.getByLabelText('模型名称'), { target: { value: 'gpt-test' } })
    fireEvent.click(screen.getByRole('button', { name: '测试临时配置' }))
    expect(await screen.findByText('连接成功，耗时 18 ms')).toBeInTheDocument()
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.objectContaining({ method: 'post', url: '/settings/model-configs/test-connection' })))
  }, 15000)

  it('uses the saved key when testing an edited config with an empty key field', async () => {
    render(<ModelSettingsPage />)
    fireEvent.click(await screen.findByRole('button', { name: /编辑/ }))
    fireEvent.click(screen.getByRole('button', { name: '测试临时配置' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.objectContaining({ method: 'post', url: '/settings/model-configs/model-1/test-connection' })), { timeout: 10000 })
    expect(await screen.findByText('连接成功，耗时 12 ms', {}, { timeout: 10000 })).toBeInTheDocument()
  }, 15000)

  it('shows a message without opening the edit dialog when testing a saved config', async () => {
    render(<ModelSettingsPage />)
    fireEvent.click(await screen.findByRole('button', { name: /测试连接/ }))
    expect(await screen.findByText('连接成功，耗时 12 ms（模型：gpt-test）')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '编辑模型配置' })).not.toBeInTheDocument()
  })

  it('blocks direct rendering for non-admin users', () => {
    systemRole = 'user'
    render(<ModelSettingsPage />)
    expect(screen.getByText('仅系统管理员可访问模型设置')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
  })
})
