import { expect, test } from 'bun:test'

import {
  KNOWN_PROVIDER_CODES,
  PROVIDER_ICON_SLUGS,
  getProviderInitial,
  getProviderTint,
  inferModelFamilyIconSlug,
  resolveModelIconSlug,
  resolveProviderIconSlug,
  resolveProviderLabel,
} from './model-provider'

function translator(known: string[] = [], has = true) {
  const t = (key: string) => `t:${key}`
  t.has = (key: string) => has && known.includes(key)
  return t
}

test('maps provider codes to icon slugs including aliases', () => {
  expect(resolveProviderIconSlug('openai')).toBe('openai')
  expect(resolveProviderIconSlug('openai_responses')).toBe('openai')
  expect(resolveProviderIconSlug('azure_openai')).toBe('azure')
  expect(resolveProviderIconSlug('siliconflow')).toBe('siliconcloud')
  expect(resolveProviderIconSlug('custom')).toBe('gateway')
  expect(resolveProviderIconSlug('  xai  ')).toBe('xai')
})

test('returns no icon for unknown or empty providers', () => {
  expect(resolveProviderIconSlug('acme')).toBeNull()
  expect(resolveProviderIconSlug('')).toBeNull()
  expect(resolveProviderIconSlug(null)).toBeNull()
  expect(resolveProviderIconSlug(undefined)).toBeNull()
})

test('known provider codes cover every mapped provider', () => {
  expect(KNOWN_PROVIDER_CODES.size).toBe(Object.keys(PROVIDER_ICON_SLUGS).length)
  for (const code of Object.keys(PROVIDER_ICON_SLUGS)) {
    expect(KNOWN_PROVIDER_CODES.has(code)).toBe(true)
  }
})

test('resolves tints for aliases and falls back for unknown providers', () => {
  expect(getProviderTint('openai')).toContain('emerald')
  expect(getProviderTint('openai_responses')).toBe(getProviderTint('openai'))
  expect(getProviderTint('siliconflow')).toBe(getProviderTint('siliconflow'))
  expect(getProviderTint('acme')).toBe(getProviderTint('custom'))
  expect(getProviderTint(null)).toBe(getProviderTint('custom'))
})

test('builds a monogram initial from the label', () => {
  expect(getProviderInitial('deepseek')).toBe('D')
  expect(getProviderInitial('  月之暗面 ')).toBe('月')
  expect(getProviderInitial('')).toBe('?')
  expect(getProviderInitial('   ')).toBe('?')
})

test('custom display names win over catalog labels', () => {
  const t = translator(['providers.deepseek'])
  expect(resolveProviderLabel(t, 'deepseek', '  Acme Gateway  ')).toBe('Acme Gateway')
  expect(resolveProviderLabel(t, 'deepseek', '   ')).toBe('t:providers.deepseek')
  expect(resolveProviderLabel(t, 'deepseek', null)).toBe('t:providers.deepseek')
})

test('uses the catalog label for known codes and the raw code otherwise', () => {
  const t = translator(['providers.deepseek'])
  expect(resolveProviderLabel(t, 'deepseek')).toBe('t:providers.deepseek')
  expect(resolveProviderLabel(t, 'acme')).toBe('acme')
  expect(resolveProviderLabel(t, '')).toBe('')
})

test('supports translators without has by checking the known provider set', () => {
  const t = ((key: string) => `t:${key}`) as ((key: string) => string) & {
    has?: (key: string) => boolean
  }
  expect(resolveProviderLabel(t, 'openai')).toBe('t:providers.openai')
  expect(resolveProviderLabel(t, 'acme')).toBe('acme')
})

test('infers model-family icons from custom gateway model ids', () => {
  expect(inferModelFamilyIconSlug('gpt-5.6-terra')).toBe('openai')
  expect(inferModelFamilyIconSlug('o3-mini')).toBe('openai')
  expect(inferModelFamilyIconSlug('gemini-3.8-flash')).toBe('google')
  expect(inferModelFamilyIconSlug('LongCat-2.0')).toBe('longcat')
  expect(inferModelFamilyIconSlug('BAAI/bge-m3')).toBe('baai')
  expect(inferModelFamilyIconSlug('BAAI/bge-reranker-v2-m3')).toBe('baai')
  expect(inferModelFamilyIconSlug('claude-sonnet')).toBe('anthropic')
  expect(inferModelFamilyIconSlug('deepseek-chat')).toBe('deepseek')
  expect(inferModelFamilyIconSlug('qwen-max')).toBe('qwen')
  expect(inferModelFamilyIconSlug('kimi-k2')).toBe('moonshot')
  expect(inferModelFamilyIconSlug('doubao-seed-1.6')).toBe('volcengine')
  expect(inferModelFamilyIconSlug('grok-4')).toBe('xai')
  expect(inferModelFamilyIconSlug('unknown-model')).toBeNull()
  expect(inferModelFamilyIconSlug('')).toBeNull()
  expect(inferModelFamilyIconSlug(null)).toBeNull()
})

test('prefers the provider icon and only infers for custom gateways', () => {
  expect(resolveModelIconSlug('openai', 'gemini-3.8-flash')).toBe('openai')
  expect(resolveModelIconSlug('custom', 'gpt-5.6-terra')).toBe('openai')
  expect(resolveModelIconSlug('custom', 'LongCat-2.0')).toBe('longcat')
  expect(resolveModelIconSlug('custom', 'unknown-model')).toBe('gateway')
  expect(resolveModelIconSlug('custom', null)).toBe('gateway')
  expect(resolveModelIconSlug('acme', 'gpt-5.6-terra')).toBeNull()
})

test('uses the inferred family tint for custom gateways', () => {
  expect(getProviderTint('custom', 'gpt-5.6-terra')).toBe(getProviderTint('openai'))
  expect(getProviderTint('custom', 'LongCat-2.0')).toContain('rose')
  expect(getProviderTint('custom', 'BAAI/bge-m3')).toContain('sky')
})
