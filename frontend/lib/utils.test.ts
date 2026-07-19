import { describe, expect, test } from 'bun:test'

import { cn, formatDate, formatDateTime, isValidEmail } from './utils'

describe('utility helpers', () => {
  test('combines conditional classes and resolves Tailwind conflicts', () => {
    expect(cn('px-2', false && 'hidden', ['block', { 'px-4': true }])).toBe('block px-4')
  })

  test('formats Date objects with zero-padded local date and time parts', () => {
    const date = new Date(2026, 1, 3, 6, 7)

    expect(formatDateTime(date)).toBe('2026/02/03 06:07')
    expect(formatDate(date)).toBe('2026/02/03')
  })

  test('accepts date strings', () => {
    expect(formatDateTime('2026-11-13T16:05:00')).toBe('2026/11/13 16:05')
    expect(formatDate('2026-11-13T16:05:00')).toBe('2026/11/13')
  })

  test('validates trimmed email-like addresses and rejects malformed values', () => {
    expect(isValidEmail('  person+tag@example.co.uk  ')).toBe(true)
    expect(isValidEmail('person@example')).toBe(false)
    expect(isValidEmail('person @example.com')).toBe(false)
    expect(isValidEmail('person@@example.com')).toBe(false)
  })
})
