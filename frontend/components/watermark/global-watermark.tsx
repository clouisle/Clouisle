'use client'

import * as React from 'react'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { authApi, type User } from '@/lib/api'
import { DEFAULT_WATERMARK_CONTENT, renderWatermarkText } from '@/lib/watermark'
import { WatermarkOverlay } from '@/components/watermark/watermark-overlay'

export function GlobalWatermark() {
  const { settings, loading } = useSiteSettings()
  const [user, setUser] = React.useState<User | null>(null)
  const [hasSession, setHasSession] = React.useState(false)
  const [identityReady, setIdentityReady] = React.useState(false)
  const [now] = React.useState(() => new Date())

  const enabled = settings.watermark_enabled

  React.useEffect(() => {
    const token = typeof window === 'undefined' ? null : localStorage.getItem('access_token')
    const session = Boolean(token)
    setHasSession(session)
    if (!enabled || !session) {
      setIdentityReady(false)
      return
    }

    let cancelled = false
    void (async () => {
      try {
        const currentUser = await authApi.getCurrentUser({ skipAuthRedirect: true, silent: true })
        if (!cancelled) setUser(currentUser)
      } catch {
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setIdentityReady(true)
      }
    })()

    return () => {
      cancelled = true
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

  if (loading || !enabled || !hasSession || !identityReady) return null

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
