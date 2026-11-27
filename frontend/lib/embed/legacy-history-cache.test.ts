import { afterEach, describe, expect, test } from 'bun:test'
import {
  LEGACY_EMBED_CHAT_HISTORY_PREFIX,
  LEGACY_EMBED_WORKFLOW_RUNS_PREFIX,
  purgeLegacyEmbedHistory,
} from '@/lib/embed/legacy-history-cache'

const originalLocalStorage = (globalThis as { localStorage?: unknown }).localStorage

function useStorage(value: unknown) {
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value, writable: true })
}

afterEach(() => {
  useStorage(originalLocalStorage)
})

describe('purgeLegacyEmbedHistory', () => {
  test('removes every entry under either legacy prefix and leaves the rest alone', () => {
    const store = new Map<string, string>([
      [`${LEGACY_EMBED_CHAT_HISTORY_PREFIX}agent-1`, 'chat'],
      [`${LEGACY_EMBED_CHAT_HISTORY_PREFIX}agent-2`, 'chat'],
      [`${LEGACY_EMBED_WORKFLOW_RUNS_PREFIX}flow-1`, 'runs'],
      ['access_token', 'keep'],
    ])
    useStorage({
      get length() { return store.size },
      key: (index: number) => Array.from(store.keys())[index] ?? null,
      removeItem: (key: string) => { store.delete(key) },
    })

    purgeLegacyEmbedHistory()

    expect([...store.keys()]).toEqual(['access_token'])
  })

  test('is a no-op without storage or key enumeration', () => {
    useStorage(undefined)
    expect(() => purgeLegacyEmbedHistory()).not.toThrow()

    useStorage({ length: 1, removeItem: () => {} })
    expect(() => purgeLegacyEmbedHistory()).not.toThrow()
  })

  test('swallows storage failures so the embed page still renders', () => {
    useStorage({
      get length(): number { throw new Error('blocked') },
      key: () => null,
      removeItem: () => {},
    })
    expect(() => purgeLegacyEmbedHistory()).not.toThrow()
  })
})
