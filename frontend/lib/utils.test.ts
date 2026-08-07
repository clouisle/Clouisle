import { describe, expect, test } from 'bun:test'

import {
  cn,
  formatDate,
  formatDateTime,
  formatDuration,
  formatTime,
  isValidEmail,
} from './utils'

describe('utility helpers', () => {
  test('combines conditional classes and resolves Tailwind conflicts', () => {
    expect(cn('px-2', false && 'hidden', ['block', { 'px-4': true }])).toBe('block px-4')
  })

  test('formats Chinese datetimes with 24h slashes and English with 12h clock', () => {
    const date = new Date(2026, 1, 3, 16, 10)

    expect(formatDateTime(date, 'zh')).toBe('2026/02/03 16:10')
    expect(formatDateTime(date, 'en')).toContain('Feb 3, 2026')
    expect(formatDateTime(date, 'en')).toContain('4:10 PM')
  })

  test('accepts ISO date strings', () => {
    expect(formatDateTime('2026-11-13T16:05:00', 'zh')).toBe('2026/11/13 16:05')
    expect(formatDateTime('2026-11-13T16:05:00', 'en')).toContain('Nov 13, 2026')
    expect(formatDateTime('2026-11-13T16:05:00', 'en')).toContain('4:05 PM')
  })

  test('parses bare YYYY-MM-DD as local date and rejects overflow', () => {
    // Bare date should be treated as local, not UTC
    expect(formatDate('2026-11-13', 'zh')).toBe('2026/11/13')
    expect(formatDate('2026-11-13', 'en')).toBe('Nov 13, 2026')
    // Overflow date (Feb 30 does not exist) should be rejected
    expect(formatDate('2026-02-30', 'en')).toBe('-')
  })

  test('formats dates with locale-specific month names', () => {
    const date = new Date(2026, 1, 3, 6, 7)

    expect(formatDate(date, 'zh')).toBe('2026/02/03')
    expect(formatDate(date, 'en')).toBe('Feb 3, 2026')
  })

  test('formats times with 24h or 12h clock by locale', () => {
    const date = new Date(2026, 1, 3, 6, 7)

    expect(formatTime(date, 'zh')).toBe('06:07')
    expect(formatTime(date, 'en')).toBe('06:07 AM')
  })

  test('honours the withSeconds option for datetime and time', () => {
    const date = new Date(2026, 1, 3, 16, 10, 30)

    expect(formatDateTime(date, 'zh', '-', { withSeconds: true })).toBe('2026/02/03 16:10:30')
    expect(formatDateTime(date, 'en', '-', { withSeconds: true })).toContain('Feb 3, 2026')
    expect(formatDateTime(date, 'en', '-', { withSeconds: true })).toContain('4:10:30 PM')
    expect(formatTime(date, 'en', '-', { withSeconds: true })).toBe('04:10:30 PM')
  })

  test('honours the withYear option for date', () => {
    const date = new Date(2026, 1, 3)

    expect(formatDate(date, 'zh', '-', { withYear: false })).toBe('02/03')
    expect(formatDate(date, 'en', '-', { withYear: false })).toBe('Feb 3')
  })

  test('falls back to a placeholder for null, empty, or invalid inputs', () => {
    expect(formatDateTime(null, 'en')).toBe('-')
    expect(formatDateTime(undefined, 'zh')).toBe('-')
    expect(formatDateTime('', 'en')).toBe('-')
    expect(formatDateTime('not-a-date', 'en')).toBe('-')

    expect(formatDate(null, 'en', 'n/a')).toBe('n/a')
    expect(formatTime(undefined, 'zh', '—')).toBe('—')
  })

  test('treats unknown locales as English', () => {
    const date = new Date(2026, 1, 3, 16, 10)

    expect(formatDateTime(date, 'fr')).toContain('Feb 3, 2026')
    expect(formatDateTime(date, 'fr')).toContain('4:10 PM')
    expect(formatDate(date, '')).toBe('Feb 3, 2026')
    expect(formatTime(date, undefined)).toBe('04:10 PM')
  })

  test('validates trimmed email-like addresses and rejects malformed values', () => {
    expect(isValidEmail('  person+tag@example.co.uk  ')).toBe(true)
    expect(isValidEmail('person@example')).toBe(false)
    expect(isValidEmail('person @example.com')).toBe(false)
    expect(isValidEmail('person@@example.com')).toBe(false)
  })

  test('formats durations with integer values and escalating units', () => {
    expect(formatDuration(0)).toBe('0ms')
    expect(formatDuration(42.5)).toBe('43ms')
    expect(formatDuration(999)).toBe('999ms')
    expect(formatDuration(1000)).toBe('1s')
    expect(formatDuration(1500)).toBe('2s')
    expect(formatDuration(59000)).toBe('59s')
    expect(formatDuration(60000)).toBe('1m')
    expect(formatDuration(90000)).toBe('2m')
    expect(formatDuration(3600000)).toBe('1h')
    expect(formatDuration(5400000)).toBe('2h')
  })
})
