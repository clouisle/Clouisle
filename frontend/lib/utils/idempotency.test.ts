import { afterEach, describe, expect, it, spyOn } from 'bun:test'

import { createIdempotencyKey } from './idempotency'

const originalCrypto = globalThis.crypto

afterEach(() => {
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: originalCrypto })
})

describe('createIdempotencyKey', () => {
  it('creates distinct keys with the requested prefix', () => {
    const first = createIdempotencyKey('tool-call')
    const second = createIdempotencyKey('tool-call')

    expect(first).toMatch(/^tool-call-/)
    expect(second).toMatch(/^tool-call-/)
    expect(first).not.toBe(second)
  })

  it('falls back to a timestamped random suffix when randomUUID is unavailable', () => {
    Object.defineProperty(globalThis, 'crypto', { configurable: true, value: {} })
    const now = spyOn(Date, 'now').mockReturnValue(1_700_000_000_000)
    const random = spyOn(Math, 'random').mockReturnValue(0.5)

    expect(createIdempotencyKey()).toBe('action-1700000000000-i')

    now.mockRestore()
    random.mockRestore()
  })
})
