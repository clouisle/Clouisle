'use client'

import * as React from 'react'
import { useTheme } from 'next-themes'
import { useSiteSettings } from '@/contexts/site-settings-context'

export function DynamicFavicon() {
  const { settings } = useSiteSettings()
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  React.useEffect(() => {
    if (!mounted) return

    // 如果设置了自定义图标，使用自定义图标，否则根据主题切换
    // 深色模式用浅色图标，浅色模式用深色图标
    const baseHref = settings.site_icon ||
      (resolvedTheme === 'dark' ? '/clouisle-light.svg' : '/clouisle-dark.svg')

    // 添加时间戳强制浏览器刷新 favicon
    const iconHref = `${baseHref}?v=${Date.now()}`

    // 移除旧的 favicon 并创建新的
    const existingLinks = document.querySelectorAll<HTMLLinkElement>("link[rel*='icon']")
    existingLinks.forEach(link => link.remove())

    const link = document.createElement('link')
    link.rel = 'icon'
    link.href = iconHref
    link.type = baseHref.endsWith('.svg') ? 'image/svg+xml' : 'image/x-icon'
    document.head.appendChild(link)
  }, [settings.site_icon, resolvedTheme, mounted])

  return null
}
