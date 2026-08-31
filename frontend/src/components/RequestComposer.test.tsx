import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RequestComposer } from './RequestComposer'

const apiMock = vi.fn()

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({
  useSession: (selector: (state: unknown) => unknown) =>
    selector({ projectId: 'project-1' }),
}))

describe('RequestComposer', () => {
  beforeEach(() => apiMock.mockReset())

  it('sends one shared preview payload and renders the masked result', async () => {
    apiMock.mockResolvedValue({ request_preview: { body: { password: '******' } }, valid: true })
    render(<RequestComposer />)

    fireEvent.change(screen.getByLabelText('环境 ID'), { target: { value: 'env-1' } })
    fireEvent.change(screen.getByLabelText('URL/Path'), { target: { value: '/login' } })
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.objectContaining({
      method: 'post',
      url: '/projects/project-1/requests/preview',
    })))
    expect(await screen.findByText(/\*\*\*\*\*\*/)).toBeInTheDocument()
  })
})
