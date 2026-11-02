export const DEFAULT_WATERMARK_CONTENT = '{username} {date} {time}'

export const WATERMARK_DEFAULTS = {
  enabled: false,
  content: DEFAULT_WATERMARK_CONTENT,
  opacity: 10,
  fontSize: 16,
  rotation: -22,
  gap: 120,
  color: '',
} as const

export const WATERMARK_LIMITS = {
  opacity: { min: 1, max: 50 },
  fontSize: { min: 10, max: 48 },
  rotation: { min: -90, max: 90 },
  gap: { min: 60, max: 600 },
} as const

export interface WatermarkTextContext {
  username?: string | null
  email?: string | null
  siteName?: string | null
  now: Date
}

const PLACEHOLDER_PATTERN = /\{(username|email|site_name|date|time)\}/g

/**
 * Render a watermark template for the current user.
 *
 * Unknown placeholders are left untouched so admins can safely include other braces.
 */
export function renderWatermarkText(
  template: string,
  context: WatermarkTextContext
): string {
  const { now } = context
  const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`

  const rendered = (template || DEFAULT_WATERMARK_CONTENT).replace(
    PLACEHOLDER_PATTERN,
    (match, key: string) => {
      switch (key) {
        case 'username':
          return context.username ?? ''
        case 'email':
          return context.email ?? ''
        case 'site_name':
          return context.siteName ?? ''
        case 'date':
          return date
        case 'time':
          return time
        default:
          return match
      }
    }
  )

  const collapsed = rendered.replace(/\s+/g, ' ').trim()
  if (collapsed) return collapsed
  return context.siteName?.trim() || 'Clouisle'
}
