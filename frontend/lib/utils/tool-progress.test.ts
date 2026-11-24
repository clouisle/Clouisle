import { describe, expect, it } from 'bun:test'
import { getToolProgressPercent } from './tool-progress'

describe('getToolProgressPercent', () => {
  it('rounds a determinate tick to a whole percentage', () => {
    expect(getToolProgressPercent({ progress: 1, total: 4 })).toBe(25)
    expect(getToolProgressPercent({ progress: 3, total: 8 })).toBe(38)
  })

  it('clamps a tick that overshoots or undershoots its total', () => {
    expect(getToolProgressPercent({ progress: 9, total: 4 })).toBe(100)
    expect(getToolProgressPercent({ progress: -2, total: 4 })).toBe(0)
  })

  it('renders nothing without a usable total', () => {
    expect(getToolProgressPercent(undefined)).toBeNull()
    expect(getToolProgressPercent({ progress: 1 })).toBeNull()
    expect(getToolProgressPercent({ progress: 1, total: null })).toBeNull()
    expect(getToolProgressPercent({ progress: 1, total: 0 })).toBeNull()
    expect(getToolProgressPercent({ progress: 1, total: Number.NaN })).toBeNull()
  })
})
