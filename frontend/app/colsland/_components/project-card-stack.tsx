'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { ProjectSelector } from './project-selector'
import { ProjectAssets } from './project-assets'

export function ProjectCardStack() {
  const t = useTranslations('platform.colslandCard')
  const [projectsOpen, setProjectsOpen] = React.useState(true)
  const [assetsOpen, setAssetsOpen] = React.useState(true)
  const [heights, setHeights] = React.useState([120, 120])
  const container = React.useRef<HTMLDivElement>(null)
  const [available, setAvailable] = React.useState(0)
  React.useEffect(() => {
    const node = container.current
    if (!node) return
    const update = () => setAvailable(node.clientHeight)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  const budget = Math.max(192, available - 16)
  const firstHeight = available && projectsOpen ? Math.min(heights[0], budget - (assetsOpen ? 96 : 56)) : heights[0]
  const secondHeight = available && assetsOpen ? Math.min(heights[1], budget - (projectsOpen ? firstHeight : 56)) : heights[1]
  const drag = React.useRef<{ index: number; y: number; height: number } | null>(null)
  const resize = (index: number, height: number) => {
    if (!available) return
    const otherHeight = index === 0 ? (assetsOpen ? secondHeight : 56) : (projectsOpen ? firstHeight : 56)
    const max = Math.max(96, available - otherHeight - 16)
    setHeights(current => current.map((value, i) => i === index ? Math.max(96, Math.min(height, max)) : value))
  }
  const controls = (index: number, open: boolean, onOpenChange: (open: boolean) => void) => ({
    open, onOpenChange, resizeLabel: t('resize'),
    onResizeStart: (event: React.PointerEvent<HTMLButtonElement>) => {
      if (event.button !== 0) return
      drag.current = { index, y: event.clientY, height: index === 0 ? firstHeight : secondHeight }
      event.currentTarget.setPointerCapture(event.pointerId)
    },
    onResizeMove: (event: React.PointerEvent<HTMLButtonElement>) => {
      if (drag.current?.index === index) resize(index, drag.current.height + event.clientY - drag.current.y)
    },
    onResizeEnd: () => { drag.current = null },
    onResizeKey: (event: React.KeyboardEvent<HTMLButtonElement>) => {
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
      event.preventDefault()
      resize(index, (index === 0 ? firstHeight : secondHeight) + (event.key === 'ArrowUp' ? -16 : 16))
    },
  })

  return (
    <div ref={container} className="flex h-[min(70dvh,40rem)] min-h-52 flex-col gap-4 overflow-y-auto lg:h-[calc(100dvh-3rem)] lg:min-h-0" aria-label={t('panels')}>
      <div className="shrink-0" style={{ height: projectsOpen ? firstHeight : undefined }}>
        <ProjectSelector {...controls(0, projectsOpen, setProjectsOpen)} />
      </div>
      <div className="shrink-0" style={{ height: assetsOpen ? secondHeight : undefined }}>
        <ProjectAssets {...controls(1, assetsOpen, setAssetsOpen)} />
      </div>
    </div>
  )
}
