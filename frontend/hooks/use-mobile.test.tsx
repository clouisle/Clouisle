import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import * as React from 'react'
import { useIsMobile } from './use-mobile'

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
const restorers: Array<{ mockRestore(): void }> = []

function installWindow(innerWidth: number) {
  const listeners = new Set<() => void>()
  const addEventListener = spyOn({ addEventListener(_type: string, listener: () => void) { listeners.add(listener) } }, 'addEventListener')
  const removeEventListener = spyOn({ removeEventListener(_type: string, listener: () => void) { listeners.delete(listener) } }, 'removeEventListener')
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      innerWidth,
      matchMedia: () => ({ addEventListener, removeEventListener }),
    },
  })
  return { addEventListener, removeEventListener, listeners }
}

afterEach(() => {
  restorers.splice(0).reverse().forEach((mock) => mock.mockRestore())
  if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
  else delete (globalThis as Record<string, unknown>).window
})

describe('useIsMobile', () => {
  it('initializes from viewport width and responds to media changes', () => {
    const browser = installWindow(767)
    let current: boolean | undefined
    const setState = spyOn({ setState(value: boolean) { current = value } }, 'setState')
    restorers.push(spyOn(React, 'useState').mockReturnValue([undefined, setState] as never))
    let cleanup: (() => void) | undefined
    restorers.push(spyOn(React, 'useEffect').mockImplementation((effect) => { cleanup = effect() as () => void }))

    expect(useIsMobile()).toBe(false)
    expect(current).toBe(true)
    expect(browser.addEventListener).toHaveBeenCalledWith('change', expect.any(Function))

    window.innerWidth = 768
    browser.listeners.forEach((listener) => listener())
    expect(current).toBe(false)

    cleanup?.()
    expect(browser.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function))
    expect(browser.listeners.size).toBe(0)
  })

  it('initializes a desktop viewport as non-mobile', () => {
    installWindow(1024)
    let current: boolean | undefined
    const setState = (value: boolean) => { current = value }
    restorers.push(spyOn(React, 'useState').mockReturnValue([undefined, setState] as never))
    restorers.push(spyOn(React, 'useEffect').mockImplementation((effect) => { effect() }))

    useIsMobile()

    expect(current).toBe(false)
  })
})
