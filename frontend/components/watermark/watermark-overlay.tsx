'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'

export interface WatermarkOverlayProps {
  text: string
  opacity: number
  fontSize: number
  rotation: number
  gap: number
  color?: string
  /** true = global fixed overlay, false = absolute layer inside a positioned parent */
  fixed?: boolean
  className?: string
}

/** Fallback advance width used before the text has been measured (0.6em per character). */
const ESTIMATED_ADVANCE = 0.6
/** Text block height relative to the font size, matching the browser's line box. */
const LINE_HEIGHT_RATIO = 1.2

export function WatermarkOverlay({
  text,
  opacity,
  fontSize,
  rotation,
  gap,
  color,
  fixed = true,
  className,
}: WatermarkOverlayProps) {
  const rawPatternId = React.useId()
  // useId() contains ":" which breaks url(#...) references.
  const patternId = `watermark-${rawPatternId.replace(/[^a-zA-Z0-9]/g, '')}`

  // Measure the real text advance instead of guessing: the rotated bounding box and therefore
  // the pitch depend on it, and a wrong guess produces either overlap or uneven gaps.
  const measureRef = React.useRef<SVGTextElement>(null)
  const measureKey = `${fontSize}:${text}`
  const [measurement, setMeasurement] = React.useState<{ key: string; width: number } | null>(null)

  React.useEffect(() => {
    let cancelled = false

    const measure = () => {
      const node = measureRef.current
      if (!node || typeof node.getComputedTextLength !== 'function') return
      const width = node.getComputedTextLength()
      if (!cancelled && width > 0) {
        setMeasurement({ key: measureKey, width: Math.ceil(width) })
      }
    }

    measure()
    // Re-measure once web fonts settle; the first pass can run against a fallback face.
    if (typeof document !== 'undefined') {
      void document.fonts?.ready.then(() => {
        if (!cancelled) measure()
      })
    }

    return () => {
      cancelled = true
    }
  }, [measureKey])

  const measuredWidth = measurement?.key === measureKey ? measurement.width : null
  const textWidth = measuredWidth ?? Math.ceil(text.length * fontSize * ESTIMATED_ADVANCE)
  const textHeight = Math.ceil(fontSize * LINE_HEIGHT_RATIO)

  // Rotated bounding box (antd computes the same rectangle from the four rotated corners).
  const radians = (rotation * Math.PI) / 180
  const cos = Math.abs(Math.cos(radians))
  const sin = Math.abs(Math.sin(radians))
  const markWidth = textWidth * cos + textHeight * sin
  const markHeight = textWidth * sin + textHeight * cos

  // Column pitch and row pitch both come from the same gap so the tiling stays even in
  // both directions; the mark itself is never clipped inside its cell.
  const pitchX = markWidth + gap
  const pitchY = markHeight + gap
  const tileWidth = pitchX * 2
  const centerX = markWidth / 2
  const centerY = markHeight / 2

  // Three marks per tile ("fill alternate"): one cell, plus the neighbouring column twice,
  // shifted up and down by half a row. This interleaves columns instead of stacking a grid.
  const marks = [
    { x: centerX, y: centerY },
    { x: centerX + pitchX, y: centerY - pitchY / 2 },
    { x: centerX + pitchX, y: centerY + pitchY / 2 },
  ]

  return (
    <div
      data-testid="watermark-overlay"
      aria-hidden="true"
      className={cn(
        'pointer-events-none select-none',
        fixed ? 'fixed inset-0 z-[9999]' : 'absolute inset-0',
        className
      )}
      style={{
        opacity: Math.min(Math.max(opacity / 100, 0), 1),
        color: color || 'var(--foreground)',
      }}
    >
      <svg className="h-full w-full">
        <text
          ref={measureRef}
          x={-10000}
          y={-10000}
          fontSize={fontSize}
          visibility="hidden"
          aria-hidden="true"
        >
          {text}
        </text>
        <defs>
          <pattern
            id={patternId}
            width={tileWidth}
            height={pitchY}
            patternUnits="userSpaceOnUse"
          >
            {marks.map(({ x, y }) => (
              <text
                key={`${x}-${y}`}
                x={x}
                y={y}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={fontSize}
                fill="currentColor"
                transform={`rotate(${rotation} ${x} ${y})`}
              >
                {text}
              </text>
            ))}
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${patternId})`} />
      </svg>
    </div>
  )
}
