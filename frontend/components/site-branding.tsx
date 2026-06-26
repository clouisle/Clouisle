'use client'

import Image from 'next/image'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { DefaultSiteIcon } from '@/components/default-site-icon'
import { getBrandingVisibility } from '@/lib/theme-config'

interface SiteBrandingProps {
  size?: 'sm' | 'md' | 'lg'
  showDescription?: boolean
  className?: string
}

export function SiteBranding({ size = 'md', showDescription = false, className = '' }: SiteBrandingProps) {
  const { settings, loading } = useSiteSettings()

  const iconSizes = {
    sm: 'size-8',
    md: 'size-12',
    lg: 'size-16',
  }

  const iconPixelSizes = {
    sm: 32,
    md: 48,
    lg: 64,
  }

  const textSizes = {
    sm: 'text-lg',
    md: 'text-2xl',
    lg: 'text-3xl',
  }

  const descSizes = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  }

  if (loading) {
    return (
      <div className={`flex flex-col items-center gap-2 ${className}`}>
        <div className={`${iconSizes[size]} rounded-lg bg-muted animate-pulse`} />
        <div className="h-6 w-24 bg-muted rounded animate-pulse" />
      </div>
    )
  }

  const { showIcon, showName } = getBrandingVisibility(settings.theme_branding_display)

  if (!showIcon && !showName) {
    return null
  }

  return (
    <div className={`flex flex-col items-center gap-2 ${className}`}>
      {showIcon && (
        <div className={`${iconSizes[size]} rounded-lg flex items-center justify-center overflow-hidden ${settings.site_icon ? 'bg-primary text-primary-foreground' : ''}`}>
          {settings.site_icon ? (
            <Image
              src={settings.site_icon}
              alt={settings.site_name}
              width={64}
              height={64}
              className="size-full object-cover"
              unoptimized
            />
          ) : (
            <DefaultSiteIcon width={iconPixelSizes[size]} height={iconPixelSizes[size]} className="size-full" />
          )}
        </div>
      )}
      {showName && (
        <h1 className={`font-bold ${textSizes[size]}`}>
          {settings.site_name || 'Clouisle'}
        </h1>
      )}
      {showName && showDescription && settings.site_description && (
        <p className={`text-muted-foreground text-center ${descSizes[size]}`}>
          {settings.site_description}
        </p>
      )}
    </div>
  )
}
