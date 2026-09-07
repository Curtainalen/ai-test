import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReportsPage } from './ReportsPage'

const apiMock = vi.fn()
const state = { projectId: 'project-1' }

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({ useSession: (selector: (value: typeof state) => unknown) => selector(state) }))

describe('ReportsPage', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockImplementation((config: { url: string }) => {
      if (config.url.endsWith('/reporting/reports')) return Promise.resolve({ items: [{ id: 'api-1', report_type: 'api', status: 'passed', summary: { total: 2 }, scenario: { name: '登录接口' }, environment: { name: '测试' }, finished_at: '2026-09-07T10:00:00+00:00' }, { id: 'ui-1', report_type: 'ui', status: 'failed', summary: { total: 3 }, scenario: { name: '登录页面' }, environment: { name: '测试' } }], total: 2 })
      if (config.url.endsWith('/reporting/summary')) return Promise.resolve({ overview: { total: 2, passed: 1, failed: 1, pass_rate: 50 }, by_type: { api: { total: 1, passed: 1, failed: 0, pass_rate: 100 }, ui: { total: 1, passed: 0, failed: 1, pass_rate: 0 } }, trend: [{ date: '2026-09-07', total: 2, passed: 1, failed: 1, canceled: 0, pass_rate: 50 }], failure_categories: [{ category: 'HTTP_ERROR', count: 1 }] })
      if (config.url.endsWith('/reporting/reports/api/api-1')) return Promise.resolve({ id: 'api-1', steps: [{ seq: 1, status: 'passed' }] })
      return Promise.resolve({})
    })
  })

  it('shows API and UI reports with a shared statistics summary', async () => {
    render(<ReportsPage />)

    expect(await screen.findByText('登录接口')).toBeInTheDocument()
    expect(screen.getByText('登录页面')).toBeInTheDocument()
    expect(screen.getAllByText('通过率').length).toBeGreaterThanOrEqual(2)
    await waitFor(() => expect(screen.getByText('50')).toBeInTheDocument())

    fireEvent.click(screen.getAllByRole('button', { name: /详\s*情/ })[0])
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith({ url: '/projects/project-1/reporting/reports/api/api-1' }))
  })
})
