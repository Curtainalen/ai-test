import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ScenarioWorkspace, createScenarioStep, moveScenarioStep, normalizeScenarioSteps } from './ScenarioWorkspace'

const apiMock = vi.hoisted(() => vi.fn())
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../store', () => ({ useSession: (selector: (state: unknown) => unknown) => selector({ projectId: 'project-1' }) }))

describe('ScenarioWorkspace', () => {
  afterEach(() => cleanup())
  beforeEach(() => apiMock.mockImplementation(({ url }: { url?: string } = {}) => Promise.resolve(
    !url ? [] :
    url.includes('api-scenario-candidates') || url.includes('requirement-test-points') ? { items: [] } : [],
  )))

  it('creates serializable ordered defaults for selected interfaces', () => {
    const login = createScenarioStep({ id: 'login', method: 'POST', path: '/login', summary: '登录' }, 7)
    const profile = createScenarioStep({ id: 'profile', method: 'GET', path: '/profile', summary: '资料' }, 3)
    expect(normalizeScenarioSteps([profile, login])).toEqual([
      expect.objectContaining({ seq: 1, interface_id: 'profile', assertions: [{ type: 'status_code', expected: 200 }] }),
      expect.objectContaining({ seq: 2, interface_id: 'login', request_override: {}, timeout_ms: 30000, retry_count: 0 }),
    ])
    expect(login.extracts).toEqual([])
    expect(login.assertions).toEqual([{ type: 'status_code', expected: 200 }])
  })

  it('moves a step and rewrites every execution sequence number', () => {
    const login = createScenarioStep({ id: 'login', method: 'POST', path: '/login', summary: '登录' }, 1)
    const profile = createScenarioStep({ id: 'profile', method: 'GET', path: '/profile', summary: '资料' }, 2)
    const logout = createScenarioStep({ id: 'logout', method: 'POST', path: '/logout', summary: '退出' }, 3)

    expect(moveScenarioStep([login, profile, logout], 2, 0)).toEqual([
      expect.objectContaining({ interface_id: 'logout', seq: 1 }),
      expect.objectContaining({ interface_id: 'login', seq: 2 }),
      expect.objectContaining({ interface_id: 'profile', seq: 3 }),
    ])
  })

  it('shows the visual editor and requirement-module multi-select', () => {
    render(<ScenarioWorkspace environments={[{ id: 'env-1', name: '测试环境', base_url: 'https://example.test', is_enabled: true }]} interfaces={[{ id: 'login', method: 'POST', path: '/login', summary: '登录', tags: ['认证'] }]} />)
    fireEvent.click(screen.getByRole('button', { name: '创建场景' }))
    expect(screen.getByRole('button', { name: /添加接口/ })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '关联已确认需求模块' })).toBeInTheDocument()
    expect(screen.queryByText('候选步骤 JSON')).not.toBeInTheDocument()
  })

  it('shows pending AI candidate differences before approval', async () => {
    apiMock.mockImplementation(({ url }: { url?: string } = {}) => {
      if (!url) return Promise.resolve([])
      if (url.includes('api-scenario-candidates')) return Promise.resolve({ items: [{
        id: 'candidate-1', interface_ids: ['login'], requirement_test_point_ids: ['point-1'],
        instruction: '覆盖登录', status: 'pending_review', revision: 2,
        content: { proposal: { name: '登录候选', description: '候选描述', priority: 'P1', requirement_test_point_ids: ['point-1'], steps: [{ seq: 1, name: '登录', interface_id: 'login', expected_result: '登录成功', assertions: [{ type: 'status_code', expected: 200 }] }] } },
      }] })
      if (url.includes('requirement-test-points')) return Promise.resolve({ items: [] })
      return Promise.resolve([])
    })
    render(<ScenarioWorkspace environments={[]} interfaces={[{ id: 'login', method: 'POST', path: '/login', summary: '登录' }]} />)
    await waitFor(() => expect(screen.getByText('登录候选')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '查看差异' }))
    expect(screen.getByText('AI 候选差异审核')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '批准候选' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '创建场景草稿' })).not.toBeInTheDocument()
  })
})
