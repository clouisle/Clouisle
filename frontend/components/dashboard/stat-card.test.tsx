import { describe, expect, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { StatCard, formatCompactNumber } from './stat-card'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
Object.assign(globalThis, {
  window: { matchMedia: () => ({ matches: true }) },
})

const Icon = () => null

function render(element: React.ReactElement) {
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(element)
  })
  return renderer
}

function text(renderer: ReactTestRenderer) {
  return JSON.stringify(renderer.toJSON())
}

describe('StatCard', () => {
  test('renders the title, formatted value, hint, and a tinted icon tile', () => {
    const renderer = render(
      <StatCard title="Total Logs" value={1234} icon={Icon} tone="blue" hint="all time" />,
    )
    const output = text(renderer)
    expect(output).toContain('Total Logs')
    expect(output).toContain('1,234')
    expect(output).toContain('all time')
    expect(output).toContain('bg-blue-500/10')
    expect(output).toContain('h-12 w-12')
  })

  test('shows a loading skeleton instead of the value while loading', () => {
    const renderer = render(<StatCard title="Total Logs" value={1234} icon={Icon} isLoading />)
    const output = text(renderer)
    expect(output).toContain('animate-pulse')
    expect(output).not.toContain('1,234')
  })

  test('renders string values verbatim and omits the icon tile when no icon is given', () => {
    const renderer = render(<StatCard title="Status" value="success" />)
    const output = text(renderer)
    expect(output).toContain('success')
    expect(output).not.toContain('h-12 w-12')
  })

  test('formats large numbers compactly when asked', () => {
    const renderer = render(<StatCard title="Tokens" value={3000000} compact />)
    expect(text(renderer)).toContain('3.0M')
  })

  test('animates the value up to its final number when animation is enabled', () => {
    const renderer = render(<StatCard title="Total Users" value={1500} animate compact />)
    expect(text(renderer)).toContain('1.5K')
  })

  test('counts the value up over time when reduced motion is not requested', async () => {
    Object.assign(globalThis, { window: { matchMedia: () => ({ matches: false }) } })
    const renderer = render(<StatCard title="Total Users" value={1500} animate />)
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1000))
    })
    expect(text(renderer)).toContain('1,500')
    act(() => renderer.unmount())
    Object.assign(globalThis, { window: { matchMedia: () => ({ matches: true }) } })
  })

  test('uses a denser layout without an icon tile in dense mode', () => {
    const renderer = render(<StatCard title="Duration" value="12 ms" dense icon={Icon} />)
    const output = text(renderer)
    expect(output).toContain('text-2xl')
    expect(output).not.toContain('h-12 w-12')
  })
})

test('formatCompactNumber abbreviates thousands and millions', () => {
  expect(formatCompactNumber(999)).toBe('999')
  expect(formatCompactNumber(1500)).toBe('1.5K')
  expect(formatCompactNumber(2500000)).toBe('2.5M')
})
