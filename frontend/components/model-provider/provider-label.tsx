'use client'

import { useProviderLabel } from '@/hooks/use-provider-label'
import { cn } from '@/lib/utils'

import { ProviderIcon } from './provider-icon'

export interface ProviderLabelProps {
  provider: string
  /** Custom gateway name; wins over the localized catalog name. */
  displayName?: string | null
  modelId?: string | null
  size?: number
  showIcon?: boolean
  className?: string
  iconClassName?: string
}

export function ProviderLabel({
  provider,
  displayName,
  modelId,
  size = 14,
  showIcon = true,
  className,
  iconClassName,
}: ProviderLabelProps) {
  const getProviderLabel = useProviderLabel()
  const label = getProviderLabel(provider, displayName)

  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1.5', className)}>
      {showIcon && (
        <ProviderIcon
          provider={provider}
          label={label}
          modelId={modelId}
          size={size}
          className={iconClassName}
        />
      )}
      <span className="truncate">{label}</span>
    </span>
  )
}
