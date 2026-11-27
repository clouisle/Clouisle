import { describe, expect, test } from 'bun:test'

import { formatHistoryKeyLabel } from './api-key-history-filter'

const labels = { inactive: 'revoked', expired: 'expired' }
const live = { name: 'Deploy key', key_prefix: 'clou_abc', is_active: true, expires_at: null }

describe('formatHistoryKeyLabel', () => {
  test('shows name and prefix for a usable key', () => {
    expect(formatHistoryKeyLabel(live, labels)).toBe('Deploy key (clou_abc)')
  })

  test('marks a revoked key even though its history stays filterable', () => {
    expect(formatHistoryKeyLabel({ ...live, is_active: false }, labels)).toBe(
      'Deploy key (clou_abc) · revoked'
    )
  })

  test('marks an expired key and prefers the revoked state when both apply', () => {
    const past = new Date(Date.now() - 60_000).toISOString()
    expect(formatHistoryKeyLabel({ ...live, expires_at: past }, labels)).toBe(
      'Deploy key (clou_abc) · expired'
    )
    expect(
      formatHistoryKeyLabel({ ...live, is_active: false, expires_at: past }, labels)
    ).toBe('Deploy key (clou_abc) · revoked')
  })

  test('does not mark a key that still has time left', () => {
    const future = new Date(Date.now() + 60_000).toISOString()
    expect(formatHistoryKeyLabel({ ...live, expires_at: future }, labels)).toBe(
      'Deploy key (clou_abc)'
    )
  })
})
