import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from './LoginPage'

const apiMock = vi.fn()
const setSessionMock = vi.fn()

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({
  useSession: (selector: (state: unknown) => unknown) =>
    selector({ setSession: setSessionMock }),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    apiMock.mockReset()
    setSessionMock.mockReset()
  })

  it('submits credentials and persists the returned session', async () => {
    const user = { id: 'u1', username: 'admin', name: 'Admin', system_role: 'admin' }
    apiMock.mockResolvedValue({ access_token: 'jwt-token', user })
    render(<LoginPage />)

    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'strong-password' } })
    fireEvent.click(screen.getByRole('button', { name: /登\s*录/ }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith({
      method: 'post',
      url: '/auth/login',
      data: { username: 'admin', password: 'strong-password' },
    }))
    expect(setSessionMock).toHaveBeenCalledWith('jwt-token', user)
  })
})
