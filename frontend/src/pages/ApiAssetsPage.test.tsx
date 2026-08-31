import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiAssetsPage } from './ApiAssetsPage'

const apiMock = vi.fn()

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({
  useSession: (selector: (state: unknown) => unknown) => selector({ projectId: 'project-1' }),
}))

describe('ApiAssetsPage', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockImplementation(({ url }: { url: string }) => {
      if (url.endsWith('/interfaces')) return Promise.resolve([])
      if (url.endsWith('/environments') || url.endsWith('/scenarios')) return Promise.resolve([])
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

  it('shows selectable added interfaces and sends only checked keys', async () => {
    apiMock.mockImplementation(({ url }: { url: string }) => {
      if (url.endsWith('/interfaces')) return Promise.resolve([])
      if (url.endsWith('/environments') || url.endsWith('/scenarios')) return Promise.resolve([])
      if (url.includes('/confirm')) return Promise.resolve({})
      return Promise.resolve({
        id: 'import-1',
        source_type: 'url',
        source_name: 'https://docs.example.com/openapi.json',
        diff: {
          added: [
            { stable_key: 'add-1', method: 'GET', path: '/one', summary: 'one' },
            { stable_key: 'add-2', method: 'POST', path: '/two', summary: 'two' },
          ],
          modified: [],
          deleted: [],
          conflicts: [],
        },
        revision: 1,
      })
    })
    render(<ApiAssetsPage />)
    fireEvent.click(screen.getByRole('button', { name: /导入/ }))
    fireEvent.click(screen.getByRole('radio', { name: 'URL 导入' }))
    fireEvent.change(screen.getByLabelText('OpenAPI 文档 URL'), {
      target: { value: 'https://docs.example.com/openapi.json' },
    })
    fireEvent.click(screen.getByRole('button', { name: '生成差异预览' }))
    await waitFor(() => expect(screen.getByText('/one')).toBeInTheDocument())
    fireEvent.click(within(screen.getByRole('row', { name: /\/one/ })).getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: '确认上传已选接口' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.objectContaining({
      data: { selected_stable_keys: ['add-2'] },
    })))
  }, 15000)

  it('opens imported interfaces in the same automation workspace and keeps scenario orchestration available', async () => {
    apiMock.mockImplementation(({ url }: { url: string }) => {
      if (url.endsWith('/interfaces')) return Promise.resolve([{
        id: 'interface-1', method: 'GET', path: '/users/{id}', summary: '查询用户', parameters: [{ name: 'id', in: 'path', example: 'u-1' }], request_body: {}, manual_config: {},
      }])
      if (url.endsWith('/environments') || url.endsWith('/scenarios')) return Promise.resolve([])
      return Promise.resolve({})
    })
    render(<ApiAssetsPage />)

    expect(await screen.findByText('/users/{id}')).toBeInTheDocument()
    expect(await screen.findByDisplayValue('/users/{id}')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '场景编排' }))
    expect(await screen.findByText('场景必须人工确认后才能创建正式执行任务')).toBeInTheDocument()
  })
})
