import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RequirementsPage } from './RequirementsPage'

const apiMock = vi.fn()
const state = { projectId: 'project-1' }

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({ useSession: (selector: (value: typeof state) => unknown) => selector(state) }))

describe('RequirementsPage', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockImplementation((config: { url: string }) => {
      if (config.url.endsWith('/requirement-reviews')) return Promise.resolve({ items: [{ id: 'review-1', requirement_module_id: 'module-1', status: 'pending_review', revision: 1, ambiguities: [], acceptance_suggestions: [] }], total: 1 })
      if (config.url.endsWith('/requirement-coverages')) return Promise.resolve({ items: [{ id: 'coverage-1', test_point_id: 'tp-1', scenario_type: 'ui', scenario_id: 'scenario-1', status: 'CANDIDATE' }], total: 1 })
      if (config.url.endsWith('/requirement-reviews/review-1')) return Promise.resolve({ id: 'review-1', requirement_module_id: 'module-1', status: 'pending_review', revision: 1, ambiguities: ['缺少锁定策略'], acceptance_suggestions: ['补充失败验收标准'], test_points: [{ id: 'tp-1', stable_key: 'login.valid', title: '正确登录', risk: 'medium', preconditions: ['账号启用'], test_data_refs: ['secret://user'], expected_result: '进入工作台' }] })
      return Promise.resolve({ items: [], total: 0 })
    })
  })

  it('shows the requirement workbench and review summaries', async () => {
    render(<RequirementsPage />)
    expect(await screen.findByText('需求文档工作台')).toBeInTheDocument()
    expect(await screen.findByText('可测性评审 (1)')).toBeInTheDocument()
    expect(await screen.findByText('需求覆盖 (1)')).toBeInTheDocument()
  })

  it('does not render an unscoped full document body by default', async () => {
    render(<RequirementsPage />)
    expect(await screen.findByText('需求文档工作台')).toBeInTheDocument()
    expect(screen.queryByText('文档正文')).not.toBeInTheDocument()
  })
})
