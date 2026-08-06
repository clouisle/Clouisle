import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
}

/**
 * 格式化耗时（毫秒）为人类可读格式
 * @param ms 毫秒数
 * @returns 格式化后的字符串，如 "42ms", "1s", "2m", "1h"
 *
 * @example
 * formatDuration(42.5)      // "43ms"
 * formatDuration(999)       // "999ms"
 * formatDuration(1500)      // "2s"
 * formatDuration(65000)     // "1m"
 * formatDuration(3661000)   // "1h"
 */
export function formatDuration(ms: number): string {
  const rounded = Math.round(ms)

  if (rounded < 1000) {
    return `${rounded}ms`
  }

  const seconds = Math.round(rounded / 1000)
  if (seconds < 60) {
    return `${seconds}s`
  }

  const minutes = Math.round(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m`
  }

  const hours = Math.round(minutes / 60)
  return `${hours}h`
}

// ---------------------------------------------------------------------------
// Locale-aware date/time formatters
// ---------------------------------------------------------------------------
//
// Centralised helpers so every surface in the app uses the same shape:
//   - zh → `2026/02/03 16:10` (zh-CN, 24h, slashes)
//   - en → `Feb 3, 2026, 4:10 PM` (en-US, 12h with AM/PM, comma)
//
// Pass the current locale (typically from next-intl's `useLocale()`) so the
// formatting matches the user's preference. Anything other than 'zh' falls
// back to the English format. null/invalid inputs return `fallback` ('-' by
// default) instead of producing 'NaN/NaN/...'.

export type SupportedDateLocale = 'en' | 'zh'

export interface DateFormatOptions {
  /** Include seconds in the output (datetime/time only). */
  withSeconds?: boolean
  /** Include the year in the date output (date only). Defaults to true. */
  withYear?: boolean
}

const ZH_LOCALE = 'zh-CN'
const EN_LOCALE = 'en-US'

const ZH_DATETIME: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
}
const EN_DATETIME: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
}
const ZH_DATE_WITH_YEAR: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}
const EN_DATE_WITH_YEAR: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
}
const ZH_DATE_NO_YEAR: Intl.DateTimeFormatOptions = {
  month: '2-digit',
  day: '2-digit',
}
const EN_DATE_NO_YEAR: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
}
const TIME: Intl.DateTimeFormatOptions = {
  hour: '2-digit',
  minute: '2-digit',
}

function parseDate(value: string | number | Date | null | undefined): Date | null {
  if (value == null || value === '') return null
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value
  }
  if (typeof value === 'string') {
    // Bare YYYY-MM-DD: parse as local date components to avoid UTC shift
    const bareDateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    if (bareDateMatch) {
      const year = parseInt(bareDateMatch[1], 10)
      const month = parseInt(bareDateMatch[2], 10)
      const day = parseInt(bareDateMatch[3], 10)
      // Reject overflow dates (e.g. 2026-02-30)
      if (month < 1 || month > 12 || day < 1) return null
      const d = new Date(0)
      d.setFullYear(year, month - 1, day)
      if (d.getMonth() !== month - 1 || d.getDate() !== day) return null
      return d
    }
  }
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

function isChinese(locale: string | null | undefined): boolean {
  return locale === 'zh'
}

function pickLocale(locale: string | null | undefined): SupportedDateLocale {
  return isChinese(locale) ? 'zh' : 'en'
}

function pick<T>(locale: SupportedDateLocale, zh: T, en: T): T {
  return locale === 'zh' ? zh : en
}

/**
 * Format a date+time using the project's locale-aware style.
 *
 * @example
 * formatDateTime(new Date(2026, 1, 3, 16, 10), 'zh') // '2026/02/03 16:10'
 * formatDateTime(new Date(2026, 1, 3, 16, 10), 'en') // 'Feb 3, 2026, 4:10 PM'
 * formatDateTime('2026-11-13T16:05:00', 'en', '-')   // 'Nov 13, 2026, 4:05 PM'
 * formatDateTime(null, 'en')                          // '-'
 */
export function formatDateTime(
  value: string | number | Date | null | undefined,
  locale: string = 'en',
  fallback: string = '-',
  options: DateFormatOptions = {},
): string {
  const d = parseDate(value)
  if (!d) return fallback
  const effective = pickLocale(locale)
  const base = pick(effective, ZH_DATETIME, EN_DATETIME)
  const fmt: Intl.DateTimeFormatOptions = options.withSeconds
    ? { ...base, second: '2-digit' }
    : base
  return d.toLocaleString(pick(effective, ZH_LOCALE, EN_LOCALE), fmt)
}

/**
 * Format a date (no time) using the project's locale-aware style.
 *
 * @example
 * formatDate(new Date(2026, 1, 3), 'zh')            // '2026/02/03'
 * formatDate(new Date(2026, 1, 3), 'en')            // 'Feb 3, 2026'
 * formatDate('2026-11-13', 'zh', '-', { withYear: false }) // '11/13'
 * formatDate('2026-11-13', 'en', '-', { withYear: false }) // 'Nov 13'
 */
export function formatDate(
  value: string | number | Date | null | undefined,
  locale: string = 'en',
  fallback: string = '-',
  options: DateFormatOptions = {},
): string {
  const d = parseDate(value)
  if (!d) return fallback
  const effective = pickLocale(locale)
  const withYear = options.withYear ?? true
  const base = withYear
    ? pick(effective, ZH_DATE_WITH_YEAR, EN_DATE_WITH_YEAR)
    : pick(effective, ZH_DATE_NO_YEAR, EN_DATE_NO_YEAR)
  return d.toLocaleDateString(pick(effective, ZH_LOCALE, EN_LOCALE), base)
}

/**
 * Format a time (no date) using the project's locale-aware style.
 *
 * @example
 * formatTime(new Date(2026, 1, 3, 16, 10), 'zh') // '16:10'
 * formatTime(new Date(2026, 1, 3, 16, 10), 'en') // '4:10 PM'
 */
export function formatTime(
  value: string | number | Date | null | undefined,
  locale: string = 'en',
  fallback: string = '-',
  options: DateFormatOptions = {},
): string {
  const d = parseDate(value)
  if (!d) return fallback
  const effective = pickLocale(locale)
  const fmt: Intl.DateTimeFormatOptions = options.withSeconds
    ? { ...TIME, second: '2-digit' }
    : TIME
  return d.toLocaleTimeString(pick(effective, ZH_LOCALE, EN_LOCALE), fmt)
}
