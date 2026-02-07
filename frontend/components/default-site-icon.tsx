'use client'

import * as React from 'react'
import Image from 'next/image'
import { useTheme } from 'next-themes'
import { cn } from '@/lib/utils'

interface DefaultSiteIconProps {
  className?: string
  width?: number
  height?: number
}

export function DefaultSiteIcon({ className, width = 32, height = 32 }: DefaultSiteIconProps) {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  // 在客户端挂载前，显示一个占位符避免闪烁
  if (!mounted) {
    return <div className={cn('bg-transparent', className)} style={{ width, height }} />
  }

  // dark 主题使用 dark 图标（白色），light 主题使用 light 图标（黑色）
  const iconSrc = resolvedTheme === 'dark' ? '/clouisle-dark.svg' : '/clouisle-light.svg'

  return (
    <Image
      src={iconSrc}
      alt="Site Icon"
      width={width}
      height={height}
      className={cn('object-contain', className)}
      unoptimized
      priority
    />
  )
}
