'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { ProjectSelector } from './project-selector'
import { ProjectAssets } from './project-assets'

export function ProjectCardStack() {
  const t = useTranslations('platform.colslandCard')
  const [projectsOpen, setProjectsOpen] = React.useState(true)
  const [assetsOpen, setAssetsOpen] = React.useState(true)
  const [split, setSplit] = React.useState(50)
  const container = React.useRef<HTMLDivElement>(null)
  const dragging = React.useRef(false)
  const resize = (clientY: number) => {
    const rect = container.current?.getBoundingClientRect()
    if (!rect || rect.height <= 0) return
    const min = Math.min(50, 96 / rect.height * 100)
    setSplit(Math.max(min, Math.min(100 - min, (clientY - rect.top) / rect.height * 100)))
  }
  const bothOpen = projectsOpen && assetsOpen

  return (
    <div ref={container} className="flex h-[min(70dvh,40rem)] min-h-52 flex-col gap-2 lg:h-[calc(100dvh-3rem)] lg:min-h-0" aria-label={t('panels')}>
      <div className="min-h-0" style={{ flex: projectsOpen ? (bothOpen ? `${split} 1 0%` : '1 1 0%') : 'none' }}>
        <ProjectSelector open={projectsOpen} onOpenChange={setProjectsOpen} />
      </div>
      {bothOpen && <div role="separator" aria-label={t('resize')} aria-orientation="horizontal" tabIndex={0} className="group flex h-3 shrink-0 touch-none cursor-row-resize items-center justify-center rounded focus-visible:outline-2 focus-visible:outline-ring"
        onPointerDown={event => { if (event.button !== 0) return; dragging.current = true; event.currentTarget.setPointerCapture(event.pointerId); resize(event.clientY) }}
        onPointerMove={event => { if (dragging.current) resize(event.clientY) }}
        onPointerUp={event => { dragging.current = false; event.currentTarget.releasePointerCapture(event.pointerId) }}
        onPointerCancel={() => { dragging.current = false }} onLostPointerCapture={() => { dragging.current = false }}
        onKeyDown={event => {
          if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
          event.preventDefault()
          const height = container.current?.getBoundingClientRect().height ?? 0
          if (!height) return
          const min = Math.min(50, 96 / height * 100)
          setSplit(value => Math.max(min, Math.min(100 - min, value + (event.key === 'ArrowUp' ? -16 : 16) / height * 100)))
        }}>
        <span className="h-1 w-10 rounded-full bg-border group-hover:bg-muted-foreground/60" />
      </div>}
      <div className="min-h-0" style={{ flex: assetsOpen ? (bothOpen ? `${100 - split} 1 0%` : '1 1 0%') : 'none' }}>
        <ProjectAssets open={assetsOpen} onOpenChange={setAssetsOpen} />
      </div>
    </div>
  )
}
