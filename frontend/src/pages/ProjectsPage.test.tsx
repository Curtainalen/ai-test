import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProjectsPage } from './ProjectsPage'

const apiMock = vi.fn()
const selectProjectMock = vi.fn()
const setProjectsMock = vi.fn()

vi.mock('../api', () => ({ api: (...args: unknown[]) => apiMock(...args) }))
vi.mock('../store', () => ({
  useSession: () => ({
    projects: [{ id: 'project-1', name: '支付平台', description: '核心项目', role: 'Owner' }],
    projectId: undefined,
    selectProject: selectProjectMock,
    setProjects: setProjectsMock,
  }),
}))

describe('ProjectsPage', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue([])
    selectProjectMock.mockReset()
    setProjectsMock.mockReset()
  })

  it('selects a project and enters its workspace when the card is clicked', () => {
    const onOpenProject = vi.fn()
    render(<ProjectsPage onOpenProject={onOpenProject} />)

    fireEvent.click(screen.getByRole('button', { name: '进入项目 支付平台' }))

    expect(selectProjectMock).toHaveBeenCalledWith('project-1')
    expect(onOpenProject).toHaveBeenCalledOnce()
  })

  it('does not provide a delete entry point', () => {
    render(<ProjectsPage />)

    expect(screen.queryByText('删除')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /删除/ })).not.toBeInTheDocument()
  })
})
