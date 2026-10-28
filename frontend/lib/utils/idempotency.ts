/** Generate a client-side idempotency key for one user action. */
export function createIdempotencyKey(prefix = 'action'): string {
  const random = globalThis.crypto?.randomUUID?.()
  if (random) return `${prefix}-${random}`
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}
