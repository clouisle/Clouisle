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
  /**
   * Decorative icons are hidden from assistive tech. Set false for icon-only
   * usage so the icon exposes an accessible name.
   */
  decorative?: boolean
}

export function ProviderIcon({
  provider,
  label,
  modelId,
  size = 16,
  className,
  decorative = true,
  'aria-label': ariaLabel,
  'aria-describedby': ariaDescribedBy,
  ...props
}: ProviderIconProps) {
  const slug = resolveModelIconSlug(provider, modelId)
  const Mark = slug ? PROVIDER_MARKS[slug] : undefined

  const accessibility = decorative
    ? { 'aria-hidden': true as const }
    : {
        role: 'img' as const,
        'aria-hidden': undefined,
        'aria-label': ariaLabel ?? label ?? provider,
        'aria-describedby': ariaDescribedBy,
      }

  if (Mark) {
    return (
      <Mark
        {...accessibility}
        data-icon={slug}
        size={size}
        className={cn('shrink-0', className)}
        {...props}
      />
    )
  }

  return (
    <span
      {...accessibility}
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
