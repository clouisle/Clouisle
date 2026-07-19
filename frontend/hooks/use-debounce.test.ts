import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'
import * as React from 'react'

let state: unknown
let effectCleanup: (() => void) | undefined
let effectDependencies: readonly unknown[] | undefined

const { useDebounce } = await import('./use-debounce')

beforeEach(() => {
  state = undefined
  effectCleanup = undefined
  effectDependencies = undefined
  Object.assign(globalThis, { window: globalThis })

  spyOn(React, 'useState').mockImplementation(<T,>(initial: T) => {
    state ??= initial
    return [state as T, (value: T) => { state = value }]
  })
  spyOn(React, 'useEffect').mockImplementation((effect, dependencies) => {
    const changed = !effectDependencies || dependencies?.some((value, index) => !Object.is(value, effectDependencies?.[index]))
    if (changed) {
      effectCleanup?.()
      effectCleanup = effect() as () => void
      effectDependencies = dependencies
    }
  })
})

afterEach(() => {
  effectCleanup?.()
  spyOn(React, 'useState').mockRestore()
  spyOn(React, 'useEffect').mockRestore()
})

function useRenderedDebounce<T>(value: T, delay = 300) {
  return useDebounce(value, delay)
}

describe('useDebounce', () => {
  test('keeps the previous value until the replacement delay elapses and cancels the stale timer', () => {
    let firstTimer: (() => void) | undefined
    let secondTimer: (() => void) | undefined
    const clearTimeout = spyOn(window, 'clearTimeout')
    const setTimeout = spyOn(window, 'setTimeout')
      .mockImplementationOnce((callback) => {
        firstTimer = callback as () => void
        return 1 as ReturnType<typeof window.setTimeout>
      })
      .mockImplementationOnce((callback) => {
        secondTimer = callback as () => void
        return 2 as ReturnType<typeof window.setTimeout>
      })

    expect(useRenderedDebounce('first')).toBe('first')
    expect(useRenderedDebounce('second')).toBe('first')
    expect(clearTimeout).toHaveBeenCalledWith(1)

    firstTimer?.()
    expect(useRenderedDebounce('second')).toBe('first')

    secondTimer?.()
    expect(useRenderedDebounce('second')).toBe('second')

    setTimeout.mockRestore()
    clearTimeout.mockRestore()
  })
})
