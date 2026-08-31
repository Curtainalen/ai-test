import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ScenarioWorkspace, createScenarioStep, moveScenarioStep, normalizeScenarioSteps } from './ScenarioWorkspace'

vi.mock('../api', () => ({ api: () => Promise.resolve([]) }))
vi.mock('../store', () => ({ useSession: (selector: (state: unknown) => unknown) => selector({ projectId: 'project-1' }) }))

describe('ScenarioWorkspace', () => {
  afterEach(() => cleanup())

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
})
