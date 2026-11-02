import { afterEach, describe, expect, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { XieyuBall, type XieyuOrbState } from './xieyu-ball'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

describe('XieyuBall', () => {
  let renderer: ReactTestRenderer | undefined
  afterEach(() => { if (renderer) act(() => renderer!.unmount()); renderer = undefined })

  test('switches business states and prioritizes them over entry interactions', async () => {
    let setup: ReactTestRenderer
    await act(async () => { setup = create(<span />) })
    const desktop = new EventTarget() as MediaQueryList
    const reduced = new EventTarget() as MediaQueryList
    Object.defineProperty(desktop, 'matches', { value: true, writable: true })
    Object.defineProperty(reduced, 'matches', { value: false, writable: true })
    const original = window.matchMedia
    window.matchMedia = (query) => query.includes('min-width') ? desktop : reduced
    try {
      await act(async () => { renderer = create(<XieyuBall />) })
      const orb = document.querySelector<SVGSVGElement>('.xieyu-orb')!
      expect(orb.dataset.expression).toBe('idle')
      await act(async () => window.dispatchEvent(new PointerEvent('pointermove', { clientX: 200, clientY: 100 })))
      expect(orb.dataset.expression).toBe('looking')
      expect(orb.style.getPropertyValue('--gaze-x')).not.toBe('')
      await act(async () => renderer!.update(<XieyuBall focused />))
      expect(orb.dataset.expression).toBe('focused')
      await act(async () => renderer!.update(<XieyuBall focused responseKey={1} />))
      expect(orb.dataset.expression).toBe('responding')
      for (const state of ['listening', 'thinking', 'working', 'waiting', 'success', 'error'] as XieyuOrbState[]) {
        await act(async () => renderer!.update(<XieyuBall state={state} focused responseKey={1} />))
        expect(orb.dataset.expression).toBe(state)
      }
      await act(async () => renderer!.update(<XieyuBall />))
      Object.defineProperty(reduced, 'matches', { value: true, writable: true })
      await act(async () => reduced.dispatchEvent(new Event('change')))
      expect(orb.style.getPropertyValue('--gaze-x')).toBe('')
      await act(async () => window.dispatchEvent(new PointerEvent('pointermove', { clientX: 500 })))
      expect(orb.dataset.expression).toBe('idle')
      expect(orb.style.getPropertyValue('--gaze-x')).toBe('')
    } finally {
      window.matchMedia = original
      act(() => setup.unmount())
    }
  })
})
