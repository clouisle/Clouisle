'use client'

import * as React from 'react'
import { ChevronDown, Grip } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useTranslations } from 'next-intl'

interface FloatingCardProps {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
}

export function FloatingCard({ title, icon, children }: FloatingCardProps) {
  const t = useTranslations('platform.colslandCard')
  const [open, setOpen] = React.useState(true)
  const [size, setSize] = React.useState({ width: 256, height: 120 })
  const drag = React.useRef<{ x: number; y: number; width: number; height: number } | null>(null)
  const updateSize = (width: number, height: number) => {
    const maxWidth = Math.max(180, Math.min(400, window.innerWidth - 48))
    const maxHeight = Math.max(96, Math.min(360, Math.floor(window.innerHeight * 0.4)))
    setSize({ width: Math.max(180, Math.min(width, maxWidth)), height: Math.max(96, Math.min(height, maxHeight)) })
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="relative max-w-full rounded-2xl border bg-card text-card-foreground shadow-lg shadow-black/5" style={{ width: size.width, maxWidth: 'min(400px, 100%)' }}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-2xl p-4 text-left text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {icon}<span className="min-w-0 flex-1 truncate">{title}</span>
        <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? '' : '-rotate-90'}`} aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent style={{ height: Math.max(40, size.height - 56), maxHeight: 'calc(40dvh - 56px)' }} className="overflow-y-auto px-4 pb-4 text-xs leading-relaxed text-muted-foreground">
        {children}
      </CollapsibleContent>
      {open && <button type="button" aria-label={t('resize', { title })} title={t('resizeHint')} className="absolute bottom-1 right-1 flex size-6 touch-none items-center justify-center rounded text-muted-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring cursor-nwse-resize"
        onPointerDown={event => { if (event.button !== 0) return; drag.current = { x: event.clientX, y: event.clientY, ...size }; event.currentTarget.setPointerCapture(event.pointerId) }}
        onPointerMove={event => { if (drag.current) updateSize(drag.current.width + event.clientX - drag.current.x, drag.current.height + event.clientY - drag.current.y) }}
        onPointerUp={event => { drag.current = null; event.currentTarget.releasePointerCapture(event.pointerId) }}
        onPointerCancel={() => { drag.current = null }}
        onLostPointerCapture={() => { drag.current = null }}
        onKeyDown={event => {
          const offsets: Record<string, [number, number]> = { ArrowLeft: [-16, 0], ArrowRight: [16, 0], ArrowUp: [0, -16], ArrowDown: [0, 16] }
          const offset = offsets[event.key]
          if (!offset) return
          event.preventDefault()
          updateSize(size.width + offset[0], size.height + offset[1])
        }}><Grip className="size-4" aria-hidden="true" /></button>}
    </Collapsible>
  )
}
