import { expect, test } from 'bun:test'
import React from 'react'

import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import { ProviderIcon } from './provider-icon'
import { PROVIDER_ICON_SLUGS } from '@/lib/model-provider'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

function renderIcon(element: React.ReactElement) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(element)
  })
  return renderer!
}

test('renders a vendored mark for every provider code', () => {
  for (const code of Object.keys(PROVIDER_ICON_SLUGS)) {
    const renderer = renderIcon(<ProviderIcon provider={code} label={code} size={20} />)
    const svg = renderer.root.findAllByType('svg')[0]
    expect(svg).toBeDefined()
    expect(svg.props.width).toBe(20)
    expect(svg.props.height).toBe(20)
    expect(svg.props['aria-hidden']).toBe(true)
    act(() => renderer.unmount())
  }
})

test('resolves provider aliases to the shared mark', () => {
  for (const code of ['openai_responses', 'azure_openai', 'siliconflow', 'custom']) {
    const renderer = renderIcon(<ProviderIcon provider={code} />)
    expect(renderer.root.findAllByType('svg')).toHaveLength(1)
    act(() => renderer.unmount())
  }
})

test('uses the model family icon for custom gateways', () => {
  const cases: Array<[string, string]> = [
    ['gpt-5.6-terra', 'openai'],
    ['gemini-3.8-flash', 'google'],
    ['LongCat-2.0', 'longcat'],
    ['BAAI/bge-m3', 'baai'],
  ]
  for (const [modelId, slug] of cases) {
    const renderer = renderIcon(<ProviderIcon provider="custom" modelId={modelId} />)
    const svg = renderer.root.findAllByType('svg')[0]
    expect(svg.props['data-icon']).toBe(slug)
    act(() => renderer.unmount())
  }
})

test('keeps the gateway mark for unknown custom model ids', () => {
  const renderer = renderIcon(<ProviderIcon provider="custom" modelId="unknown-model" />)
  expect(renderer.root.findAllByType('svg')[0].props['data-icon']).toBe('gateway')
  act(() => renderer.unmount())
})

test('falls back to a tinted monogram for unknown providers', () => {
  const renderer = renderIcon(<ProviderIcon provider="acme" label="Acme Gateway" size={24} />)

  expect(renderer.root.findAllByType('svg')).toHaveLength(0)
  const tile = renderer.root.findAllByType('span')[0]
  expect(tile.children).toEqual(['A'])
  expect(tile.props['aria-hidden']).toBe(true)
  expect(tile.props.style).toEqual({ width: 24, height: 24, fontSize: 13 })
  act(() => renderer.unmount())
})

test('uses the provider code for the monogram when no label is given', () => {
  const renderer = renderIcon(<ProviderIcon provider="zhipu-proxy" size={16} />)
  expect(renderer.root.findAllByType('span')[0].children).toEqual(['Z'])
  act(() => renderer.unmount())
})

test('supports a nondecorative monogram with an accessible name', () => {
  const renderer = renderIcon(
    <ProviderIcon provider="acme" label="Acme Gateway" decorative={false} aria-label="Acme Gateway" />,
  )
  const tile = renderer.root.findAllByType('span')[0]
  expect(tile.props.role).toBe('img')
  expect(tile.props['aria-label']).toBe('Acme Gateway')
  expect(tile.props['aria-hidden']).toBeUndefined()
  act(() => renderer.unmount())
})

test('supports a nondecorative brand mark with an accessible name', () => {
  const renderer = renderIcon(
    <ProviderIcon provider="openai" decorative={false} aria-label="OpenAI" />,
  )
  const svg = renderer.root.findAllByType('svg')[0]
  expect(svg.props.role).toBe('img')
  expect(svg.props['aria-label']).toBe('OpenAI')
  expect(svg.props['aria-hidden']).toBeUndefined()
  act(() => renderer.unmount())
})

test('forwards className and svg props', () => {
  const renderer = renderIcon(
    <ProviderIcon provider="openai" className="mr-1" data-testid="mark" />,
  )
  const svg = renderer.root.findAllByType('svg')[0]
  expect(svg.props.className).toContain('mr-1')
  expect(svg.props['data-testid']).toBe('mark')
  act(() => renderer.unmount())
})
