import { afterEach, describe, expect, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { XieyuBall, type XieyuOrbState } from './xieyu-ball'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

describe('XieyuBall', () => {
  let renderer: ReactTestRenderer | undefined
  afterEach(() => { if (renderer) act(() => renderer!.unmount()); renderer = undefined })

  test('renders upstream expressions and cleans up across motion and viewport changes', async () => {
    let setup: ReactTestRenderer
    await act(async () => { setup = create(<span />) })
    const desktop = new EventTarget() as MediaQueryList
    const reduced = new EventTarget() as MediaQueryList
    Object.defineProperty(desktop, 'matches', { value: true, writable: true })
    Object.defineProperty(reduced, 'matches', { value: true, writable: true })
    const original = window.matchMedia
    window.matchMedia = (query) => query.includes('min-width') ? desktop : reduced
    try {
      await act(async () => { renderer = create(<XieyuBall />) })
      const orb = document.querySelector<HTMLElement>('.xieyu-orb')!
      const paths = () => Array.from(orb.querySelectorAll('svg > g:nth-of-type(2) path')).map(path => path.getAttribute('d'))
      expect(orb.querySelector('svg')?.getAttribute('viewBox')).toBe('-15 -15 259 259')
      const idle = paths()
      expect(idle.length).toBeGreaterThanOrEqual(3)
      for (const state of ['listening', 'thinking', 'working', 'waiting', 'success', 'error'] as XieyuOrbState[]) {
        await act(async () => renderer!.update(<XieyuBall state={state} focused responseKey={1} />))
        expect(paths()).not.toEqual(idle)
      }
      await act(async () => renderer!.update(<XieyuBall focused />))
      expect(paths()).not.toEqual(idle)
      Object.defineProperty(reduced, 'matches', { value: false, writable: true })
      await act(async () => reduced.dispatchEvent(new Event('change')))
      expect(orb.querySelector('svg')).not.toBeNull()
      await act(async () => window.dispatchEvent(new PointerEvent('pointermove', { clientX: 200, clientY: 100 })))
      await act(async () => renderer!.update(<XieyuBall responseKey={2} />))
      await act(async () => renderer!.unmount())
      renderer = undefined
      expect(orb.querySelector('svg')).toBeNull()
    } finally {
      window.matchMedia = original
      act(() => setup.unmount())
    }
  })
})
