import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 格式化日期时间为 2026/02/03 16:10 格式
 */
export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${year}/${month}/${day} ${hour}:${minute}`
}

/**
 * 格式化日期为 2026/02/03 格式
 */
export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}/${month}/${day}`
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
