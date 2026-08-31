import { describe, expect, it } from 'vitest'

import { appMenuItems } from './App'

describe('appMenuItems', () => {
  it('shows model settings only to system administrators', () => {
    expect(appMenuItems('admin').some((item) => item.key === 'model-settings')).toBe(true)
    expect(appMenuItems('user').some((item) => item.key === 'model-settings')).toBe(false)
  })

  it('shows user management only to system administrators', () => {
    expect(appMenuItems('admin').some((item) => item.key === 'users')).toBe(true)
    expect(appMenuItems('user').some((item) => item.key === 'users')).toBe(false)
  })
})
