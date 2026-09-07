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
      if (config.url.endsWith('/requirement-coverages')) return Promise.resolve({ items: [{ id: 'coverage-1', test_point_id: 'tp-1', scenario_type: 'ui', scenario_id: 'scenario-1', status: 'CANDIDATE' }], total: 1 })
      return Promise.resolve({ items: [], total: 0 })
    })
  })

  it('shows the requirement workbench and test case summaries', async () => {
    render(<RequirementsPage />)
    expect(await screen.findByText('需求文档工作台')).toBeInTheDocument()
    expect(await screen.findByText('测试用例 (0)')).toBeInTheDocument()
    expect(await screen.findByText('需求覆盖 (1)')).toBeInTheDocument()
  })

  it('does not render an unscoped full document body by default', async () => {
    render(<RequirementsPage />)
    expect(await screen.findByText('需求文档工作台')).toBeInTheDocument()
    expect(screen.queryByText('文档正文')).not.toBeInTheDocument()
  })
})
