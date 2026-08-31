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

  it('shows review, coverage and pending approval details', async () => {
    render(<RequirementsPage />)
    expect(await screen.findByText('可测性评审候选')).toBeInTheDocument()
    expect(await screen.findByText('CANDIDATE')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看评审' }))
    expect(await screen.findByText('正确登录')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /批准/ })).toBeInTheDocument()
  })
})
