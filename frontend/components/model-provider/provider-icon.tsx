'use client'

import type { SVGProps } from 'react'

import { getProviderInitial, getProviderTint, resolveModelIconSlug } from '@/lib/model-provider'
import { cn } from '@/lib/utils'

import { PROVIDER_MARKS } from './icons'

export interface ProviderIconProps extends Omit<SVGProps<SVGSVGElement>, 'size'> {
  /** Provider code from the backend, e.g. `openai`, `azure_openai`. */
  provider: string
  /** Human-readable label used by the monogram fallback. */
  label?: string
  /** Backend model_id. Used to pick a family icon for custom gateways. */
  modelId?: string | null
  size?: number
  className?: string
}

export function ProviderIcon({
  provider,
  label,
  modelId,
  size = 16,
  className,
  ...props
}: ProviderIconProps) {
  const slug = resolveModelIconSlug(provider, modelId)
  const Mark = slug ? PROVIDER_MARKS[slug] : undefined

  if (Mark) {
    return (
      <Mark
        aria-hidden="true"
        data-icon={slug}
        size={size}
        className={cn('shrink-0', className)}
        {...props}
      />
    )
  }

  return (
    <span
      aria-hidden="true"
      data-icon="monogram"
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded font-semibold leading-none',
        getProviderTint(provider, modelId),
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.55)) }}
    >
      {getProviderInitial(label || provider)}
    </span>
  )
}
