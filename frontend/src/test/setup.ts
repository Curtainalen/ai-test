import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { message, notification } from 'antd'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
  message.destroy()
  notification.destroy()
})

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverStub

const getComputedStyle = window.getComputedStyle.bind(window)
window.getComputedStyle = (element: Element, pseudoElement?: string | null) =>
  getComputedStyle(element, pseudoElement ? null : pseudoElement)
