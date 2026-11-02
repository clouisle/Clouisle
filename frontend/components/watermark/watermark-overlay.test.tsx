import { describe, expect, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestInstance, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { WatermarkOverlay, type WatermarkOverlayProps } from './watermark-overlay'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = (props: WatermarkOverlayProps) => {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<WatermarkOverlay {...props} />)
  })
  const result = renderer!
  const layer = result.root
    .findAllByType('div')
    .find((element: ReactTestInstance) => element.props['data-testid'] === 'watermark-overlay')!
  return { renderer: result, layer, root: result.root }
}

const BASE = { text: 'alice 2026-11-02 09:07', opacity: 10, fontSize: 16, rotation: -30, gap: 180 }

describe('WatermarkOverlay', () => {
  test('tiles three marks per pattern cell in the antd fill-alternate layout', () => {
    const { root } = render(BASE)
    const pattern = root.findByType('pattern')
    // Rotating the whole pattern would clip text at the tile edges.
    expect(pattern.props.patternTransform).toBeUndefined()

    const patternMarkup = pattern.findAllByType('text')
    expect(patternMarkup).toHaveLength(3)
    const [first, above, below] = patternMarkup
    const pitchX = pattern.props.width / 2
    const pitchY = pattern.props.height

    expect(above.props.x).toBe(first.props.x + pitchX)
    expect(below.props.x).toBe(above.props.x)
    expect(above.props.y).toBe(first.props.y - pitchY / 2)
    expect(below.props.y).toBe(first.props.y + pitchY / 2)

    for (const mark of patternMarkup) {
      expect(mark.props.transform).toBe(
        `rotate(-30 ${mark.props.x} ${mark.props.y})`
      )
      expect(mark.props.children).toBe(BASE.text)
    }

    // One hidden copy measures the real text advance for the rotated bounding box.
    const hidden = root.findAllByType('text').filter((node) => node.props.visibility === 'hidden')
    expect(hidden).toHaveLength(1)
    expect(hidden[0].props.children).toBe(BASE.text)

    const rect = root.findByType('rect')
    expect(rect.props.fill).toBe(`url(#${pattern.props.id})`)
    expect(pattern.props.id).not.toContain(':')
  })

  test('uses the fixed layer globally and an absolute layer for previews', () => {
    expect(render(BASE).layer.props.className).toContain('fixed inset-0 z-[9999]')
    expect(render({ ...BASE, fixed: false }).layer.props.className).toContain('absolute inset-0')
  })

  test('clamps opacity and falls back to the theme foreground', () => {
    expect(render({ ...BASE, opacity: 0 }).layer.props.style.opacity).toBe(0)
    expect(render({ ...BASE, opacity: 100 }).layer.props.style.opacity).toBe(1)
    expect(render({ ...BASE, opacity: 10 }).layer.props.style.opacity).toBe(0.1)
    expect(render({ ...BASE, opacity: 10 }).layer.props.style.color).toBe('var(--foreground)')
    expect(render({ ...BASE, color: '#ff0000' }).layer.props.style.color).toBe('#ff0000')
  })
})
