import { expect, mock, test } from 'bun:test'
import React from 'react'

import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('next-intl', () => ({
  useTranslations: () => {
    const t = (key: string) => (key === 'providers.deepseek' ? 'DeepSeek Localized' : key)
    t.has = (key: string) => key === 'providers.deepseek'
    return t
  },
}))

const { ProviderLabel } = await import('./provider-label')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

function renderLabel(element: React.ReactElement) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(element)
  })
  return renderer!
}

test('renders the localized provider name with its icon', () => {
  const renderer = renderLabel(<ProviderLabel provider="deepseek" />)

  expect(renderer.root.findAllByType('svg')).toHaveLength(1)
  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('DeepSeek Localized'))).toBe(true)
  act(() => renderer.unmount())
})

test('prefers a custom gateway display name', () => {
  const renderer = renderLabel(
    <ProviderLabel provider="custom" displayName="  Acme AI Gateway  " />,
  )

  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('Acme AI Gateway'))).toBe(true)
  act(() => renderer.unmount())
})

test('falls back to the provider code for unknown providers', () => {
  const renderer = renderLabel(<ProviderLabel provider="acme" />)

  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('acme'))).toBe(true)
  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('A'))).toBe(true)
  act(() => renderer.unmount())
})

test('uses the model family icon for custom gateways', () => {
  const renderer = renderLabel(<ProviderLabel provider="custom" modelId="gpt-5.6-terra" />)

  expect(renderer.root.findAllByType('svg')[0].props['data-icon']).toBe('openai')
  act(() => renderer.unmount())
})

test('can hide the icon while keeping the label', () => {
  const renderer = renderLabel(<ProviderLabel provider="deepseek" showIcon={false} />)

  expect(renderer.root.findAllByType('svg')).toHaveLength(0)
  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('DeepSeek Localized'))).toBe(true)
  act(() => renderer.unmount())
})
