'use client'

import * as React from 'react'
import { Card, CardContent } from '@/components/ui/card'

export type StatCardTone = 'primary' | 'blue' | 'purple' | 'green' | 'orange' | 'cyan' | 'red'

export const STAT_CARD_TONE_CLASSES: Record<StatCardTone, string> = {
  primary: 'bg-primary/10 text-primary',
  blue: 'bg-blue-500/10 text-blue-500',
  purple: 'bg-purple-500/10 text-purple-500',
  green: 'bg-green-500/10 text-green-500',
  orange: 'bg-orange-500/10 text-orange-500',
  cyan: 'bg-cyan-500/10 text-cyan-500',
  red: 'bg-red-500/10 text-red-500',
}

export function formatCompactNumber(num: number): string {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function useCountUp(value: number, active: boolean) {
  const [displayValue, setDisplayValue] = React.useState(0)

  React.useEffect(() => {
    if (!active) {
      setDisplayValue(value)
      return
    }
    if (prefersReducedMotion() || value === 0) {
      setDisplayValue(value)
      return
    }

    const duration = 900
    const startedAt = performance.now()
    let frameId = 0

    const tick = (now: number) => {
      const progress = Math.min((now - startedAt) / duration, 1)
      const easedProgress = 1 - Math.pow(1 - progress, 3)
      setDisplayValue(Math.round(value * easedProgress))
      if (progress < 1) frameId = requestAnimationFrame(tick)
    }

    frameId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameId)
  }, [active, value])

  return displayValue
}

export interface StatCardProps {
  title: string
  value: number | string
  icon?: React.ElementType
  tone?: StatCardTone
  hint?: string
  isLoading?: boolean
  /** Render large numbers as 1.2K / 3.0M instead of the exact value. */
  compact?: boolean
  /** Animate the value counting up to its final number. */
  animate?: boolean
  /** Compact layout for inline panels (smaller value, no icon tile). */
  dense?: boolean
  className?: string
}

export function StatCard({
  title,
  value,
  icon: Icon,
  tone = 'primary',
  hint,
  isLoading = false,
  compact = false,
  animate = false,
  dense = false,
  className,
}: StatCardProps) {
  const numericValue = typeof value === 'number' ? value : 0
  const animatedValue = useCountUp(numericValue, animate && !isLoading)
  const shownValue = animate ? animatedValue : numericValue
  const displayValue =
    typeof value === 'number'
      ? compact
        ? formatCompactNumber(shownValue)
        : shownValue.toLocaleString()
      : value

  return (
    <Card size="sm" className={`hover:shadow-md transition-shadow ${className ?? ''}`}>
      <CardContent className="py-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <p className="truncate text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <div className="h-9 w-32 rounded bg-muted animate-pulse" />
            ) : (
              <p className={dense ? 'text-2xl font-bold tracking-tight' : 'text-3xl font-bold tracking-tight'}>
                {displayValue}
              </p>
            )}
            {hint && !isLoading && <p className="text-xs text-muted-foreground">{hint}</p>}
          </div>
          {Icon && !dense && (
            <div
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${STAT_CARD_TONE_CLASSES[tone]}`}
            >
              <Icon className="h-6 w-6" />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
