import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RequestComposer } from './RequestComposer'

const apiMock = vi.fn()

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({
  useSession: (selector: (state: unknown) => unknown) => selector({ projectId: 'project-1' }),
}))

const interfaceAsset = {
  id: 'interface-1',
  method: 'POST',
  path: '/login',
  summary: '用户登录',
  parameters: [{ name: 'locale', in: 'query', example: 'zh-CN' }],
  request_body: { content: { 'application/json': { example: { username: 'demo' } } } },
}

describe('RequestComposer', () => {
  beforeEach(() => apiMock.mockReset())

  it('loads the selected interface and sends the shared preview payload with its asset id', async () => {
    apiMock.mockResolvedValue({ request_preview: { body: { password: '******' } }, valid: true })
    render(<RequestComposer interfaceAsset={interfaceAsset} environments={[{ id: 'env-1', name: '开发', base_url: 'https://api.example.test', is_enabled: true }]} />)

    expect(await screen.findByDisplayValue('/login')).toBeInTheDocument()
    expect(screen.getByDisplayValue(/locale/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.objectContaining({
      method: 'post',
      url: '/projects/project-1/requests/preview',
      data: expect.objectContaining({
        environment_id: 'env-1',
        interface_id: 'interface-1',
        request: expect.objectContaining({ assertions: [{ type: 'status_code', expected: 200 }] }),
      }),
    })))
    expect(await screen.findByText(/\*\*\*\*\*\*/)).toBeInTheDocument()
  })
})
