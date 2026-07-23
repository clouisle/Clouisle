import { describe, expect, test } from 'bun:test'

import {
  CHART_AXIS_COLOR,
  CHART_COLOR_ORDER,
  CHART_GRID_COLOR,
  CHART_HOVER_CURSOR,
  CHART_SURFACE_COLORS,
  CHART_TOOLTIP_STYLE,
} from './chart-theme'

describe('chart theme', () => {
  test('keeps the intentional series order and derives translucent surfaces from it', () => {
    expect(CHART_COLOR_ORDER).toEqual([
      'var(--chart-1)',
      'var(--chart-2)',
      'var(--chart-3)',
      'var(--chart-5)',
      'var(--chart-4)',
      'var(--chart-6)',
      'var(--chart-7)',
      'var(--chart-8)',
      'var(--chart-9)',
      'var(--chart-10)',
    ])
    expect(CHART_SURFACE_COLORS).toEqual(
      CHART_COLOR_ORDER.map((color) => `color-mix(in srgb, ${color} 78%, transparent)`),
    )
  })

  test('uses chart CSS variables for shared primitives', () => {
    expect(CHART_AXIS_COLOR).toBe('var(--chart-axis)')
    expect(CHART_GRID_COLOR).toBe('var(--chart-grid)')
    expect(CHART_TOOLTIP_STYLE).toEqual({
      backgroundColor: 'var(--chart-tooltip-bg)',
      borderColor: 'var(--chart-tooltip-border)',
      color: 'var(--chart-tooltip-text)',
    })
    expect(CHART_HOVER_CURSOR).toEqual({
      fill: 'var(--chart-crosshair)',
      fillOpacity: 0.32,
    })
  })
})
