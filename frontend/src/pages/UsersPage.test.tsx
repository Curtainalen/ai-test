import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UsersPage } from './UsersPage'

const apiMock = vi.fn()
let actor = { id: 'admin-1', username: 'admin', name: '管理员', system_role: 'admin' }

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({ useSession: (selector: (state: unknown) => unknown) => selector({ user: actor }) }))

describe('UsersPage', () => {
  beforeEach(() => {
    actor = { id: 'admin-1', username: 'admin', name: '管理员', system_role: 'admin' }
    apiMock.mockReset()
    apiMock.mockResolvedValue([
      { id: 'admin-1', username: 'admin', name: '管理员', email: 'admin@example.test', system_role: 'admin', is_active: true, last_login_at: null },
      { id: 'member-1', username: 'member', name: '成员', email: '', system_role: 'user', is_active: true, last_login_at: null },
    ])
  })
  afterEach(() => cleanup())

  it('renders the user list', async () => {
    render(<UsersPage />)
    expect(await screen.findByText('admin')).toBeInTheDocument()
    expect(screen.getByText('member')).toBeInTheDocument()
    expect(screen.getAllByText('管理员').length).toBeGreaterThan(0)
  })

  it('disables the current user activation switch', async () => {
    render(<UsersPage />)
    expect(await screen.findByRole('switch', { name: 'admin 状态' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'member 状态' })).not.toBeDisabled()
  })

  it('opens a user creation form with password validation', async () => {
    render(<UsersPage />)
    fireEvent.click(await screen.findByRole('button', { name: '新增用户' }))
    expect(screen.getByRole('dialog', { name: '新增用户' })).toBeInTheDocument()
    expect(screen.getByLabelText('密码')).toBeInTheDocument()
  })

  it('blocks non-admin rendering', () => {
    actor = { id: 'member-1', username: 'member', name: '成员', system_role: 'user' }
    render(<UsersPage />)
    expect(screen.getByText('仅系统管理员可访问用户管理')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
  })
})
