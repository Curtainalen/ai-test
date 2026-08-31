import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiAssetsPage } from './ApiAssetsPage'

const apiMock = vi.fn()

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({
  useSession: (selector: (state: unknown) => unknown) => selector({ projectId: 'project-1' }),
}))

describe('ApiAssetsPage', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockImplementation(({ url }: { url: string }) => {
      if (url.endsWith('/interfaces')) return Promise.resolve([])
      return Promise.resolve({
        id: 'import-1',
        source_type: 'url',
        source_name: 'https://docs.example.com/openapi.json',
        diff: { added: [], modified: [], deleted: [], conflicts: [] },
        revision: 1,
      })
    })
  })

  it('submits a URL import with one-time authentication settings', async () => {
    render(<ApiAssetsPage />)
    fireEvent.click(screen.getByRole('button', { name: /导入/ }))
    fireEvent.click(screen.getByRole('radio', { name: 'URL 导入' }))
    fireEvent.change(screen.getByLabelText('OpenAPI 文档 URL'), {
      target: { value: 'https://docs.example.com/openapi.json' },
    })
    fireEvent.click(screen.getByRole('button', { name: '生成差异预览' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith({
      method: 'post',
      url: '/projects/project-1/api-imports/url',
      data: {
        url: 'https://docs.example.com/openapi.json',
        auth: {
          type: 'none',
          username: undefined,
          password: undefined,
          token: undefined,
          header_name: undefined,
          header_value: undefined,
        },
      },
    }))
  })
})
