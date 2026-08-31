import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UiAutomationPage } from './UiAutomationPage'

const apiMock = vi.fn()
const state = { projectId: 'project-1' }

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({ useSession: (selector: (value: typeof state) => unknown) => selector(state) }))

describe('UiAutomationPage', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockImplementation((config: { url: string; method?: string }) => {
      if (config.method === 'post' && config.url.includes('/elements/element-1/verify')) return Promise.resolve({ status: 'failed', match_count: 2, visible: true, actionable: true, error_message: '定位器不唯一' })
      if (config.url.endsWith('/ui/elements')) return Promise.resolve({ items: [{ id: 'element-1', page_id: 'page-1', name: '登录按钮', primary_locator: { type: 'test_id', value: 'login' }, fallback_locators: [], verified: false, revision: 1 }], total: 1 })
      if (config.url.endsWith('/ui/reports')) return Promise.resolve({ items: [{ id: 'report-123456789', execution_id: 'execution-1', status: 'failed', trace_manifest_ref: 'trace-1', finished_at: '2026-08-31' }], total: 1 })
      if (config.url.endsWith('/ui/reports/report-123456789')) return Promise.resolve({ id: 'report-123456789', execution_id: 'execution-1', status: 'failed', trace_manifest_ref: 'trace-1', steps: [{ seq: 1, name: '登录', status: 'failed', error_category: 'LOCATOR_BROKEN', error_message: '未找到元素', duration_ms: 10, evidence_refs: ['evidence-1'] }] })
      if (config.url.endsWith('/ui/modules') || config.url.endsWith('/ui/pages') || config.url.endsWith('/ui/page-steps') || config.url.endsWith('/ui/scenarios') || config.url.endsWith('/ui/verifications')) return Promise.resolve({ items: [], total: 0 })
      if (config.url.endsWith('/environments')) return Promise.resolve([{ id: 'env-1', name: '测试', is_enabled: true }])
      return Promise.resolve({ items: [], total: 0 })
    })
  })

  it('uses the AI test workflow as the primary entry and keeps assets advanced', async () => {
    render(<UiAutomationPage />)
    expect(await screen.findByText('从测试目标生成可审核的浏览器测试流程，确认后再执行。')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /新建 AI 测试/ })[0])
    expect(await screen.findByLabelText('测试目标')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /database 高级资产/ }))
    expect(await screen.findByText('仅在需要细调定位器、排查验证或维护历史资产时使用。常规流程从“新建 AI 测试”开始。')).toBeInTheDocument()
  }, 10000)

  it('shows failure classification and controlled evidence references in report details', async () => {
    render(<UiAutomationPage />)
    fireEvent.click(await screen.findByRole('tab', { name: '执行报告' }))
    fireEvent.click(await screen.findByRole('button', { name: /查看/ }))
    expect(await screen.findByText('LOCATOR_BROKEN')).toBeInTheDocument()
    expect(screen.getByText('trace-1')).toBeInTheDocument()
    expect(screen.getByText('evidence-1')).toBeInTheDocument()
  }, 10000)
})
