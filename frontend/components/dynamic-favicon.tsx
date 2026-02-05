'use client'

import * as React from 'react'
import { useSiteSettings } from '@/contexts/site-settings-context'

export function DynamicFavicon() {
  const { settings } = useSiteSettings()

  React.useEffect(() => {
    // 如果设置了自定义图标，使用自定义图标，否则使用固定的 light icon
    const iconHref = settings.site_icon || '/clouisle-light.svg'

    // 更新 favicon
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']")
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = iconHref
    link.type = iconHref.endsWith('.svg') ? 'image/svg+xml' : 'image/x-icon'
  }, [settings.site_icon])

  return null
}
