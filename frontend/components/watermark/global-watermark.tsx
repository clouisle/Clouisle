'use client'

import * as React from 'react'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { authApi, type User } from '@/lib/api'
import { DEFAULT_WATERMARK_CONTENT, renderWatermarkText } from '@/lib/watermark'
import { WatermarkOverlay } from '@/components/watermark/watermark-overlay'
const MINUTE_ROLLOVER_BUFFER_MS = 50
const FALLBACK_CHECK_MS = 5_000

function readAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('access_token')
}

export function GlobalWatermark() {
  const { settings, loading } = useSiteSettings()
  const [token, setToken] = React.useState<string | null>(null)
  const [user, setUser] = React.useState<User | null>(null)
  const [now, setNow] = React.useState(() => new Date())

  const enabled = settings.watermark_enabled

  // Track the session token: signing in or out in another tab replaces it in shared storage.
  React.useEffect(() => {
    setToken(readAccessToken())
    if (typeof window === 'undefined') return

    const onStorage = (event: StorageEvent) => {
      if (event.key === 'access_token' || event.key === null) {
        setToken(readAccessToken())
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  // The overlay only ever shows an identity that was resolved for the current token.
  React.useEffect(() => {
    setUser(null)
    if (!enabled || !token) return

    let cancelled = false
    void (async () => {
      try {
        const currentUser = await authApi.getCurrentUser({
          skipAuthRedirect: true,
          silent: true,
        })
        if (!cancelled) setUser(currentUser)
      } catch {
        if (!cancelled) setUser(null)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [enabled, token])

  // Keep {date} and {time} current across minute and day boundaries.
  // Ticks precisely at the minute rollover (:00.050), checks periodically as fallback,
  // and syncs immediately when returning to the tab.
  React.useEffect(() => {
    if (!enabled) return

    let timer: NodeJS.Timeout | number | undefined
    let cancelled = false

    const tick = () => {
      setNow(new Date())
    }

    const scheduleTick = () => {
      const nowMs = Date.now()
      const delay = Math.max(50, 60_000 - (nowMs % 60_000) + MINUTE_ROLLOVER_BUFFER_MS)
      timer = setTimeout(() => {
        if (cancelled) return
        tick()
        scheduleTick()
      }, delay)
    }

    scheduleTick()

    let lastMinute = Math.floor(Date.now() / 60_000)
    const fallbackInterval = setInterval(() => {
      const currentMinute = Math.floor(Date.now() / 60_000)
      if (currentMinute !== lastMinute) {
        lastMinute = currentMinute
        tick()
      }
    }, FALLBACK_CHECK_MS)

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        lastMinute = Math.floor(Date.now() / 60_000)
        tick()
        clearTimeout(timer)
        scheduleTick()
      }
    }
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }

    return () => {
      cancelled = true
      clearTimeout(timer)
      clearInterval(fallbackInterval)
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibilityChange)
      }
    }
  }, [enabled])

  const text = React.useMemo(
    () =>
      renderWatermarkText(settings.watermark_content || DEFAULT_WATERMARK_CONTENT, {
        username: user?.username,
        email: user?.email,
        siteName: settings.site_name,
        now,
      }),
    [settings.watermark_content, settings.site_name, user?.username, user?.email, now]
  )

  if (loading || !enabled || !token || !user) return null

  return (
    <WatermarkOverlay
      text={text}
      opacity={settings.watermark_opacity}
      fontSize={settings.watermark_font_size}
      rotation={settings.watermark_rotation}
      gap={settings.watermark_gap}
      color={settings.watermark_color}
      fixed
    />
  )
}
