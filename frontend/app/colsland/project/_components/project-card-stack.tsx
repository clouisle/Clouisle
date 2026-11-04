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
  const [widths, setWidths] = React.useState([256, 256])
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
  const drag = React.useRef<{ index: number; x: number; y: number; width: number; height: number } | null>(null)
  const resize = (index: number, width: number, height: number) => {
    if (!available) return
    const maxWidth = Math.max(180, Math.min(400, container.current?.clientWidth || window.innerWidth - 48))
    setWidths(current => current.map((value, i) => i === index ? Math.max(180, Math.min(width, maxWidth)) : value))
    const otherHeight = index === 0 ? (assetsOpen ? secondHeight : 56) : (projectsOpen ? firstHeight : 56)
    const max = Math.max(96, available - otherHeight - 16)
    setHeights(current => current.map((value, i) => i === index ? Math.max(96, Math.min(height, max)) : value))
  }
  const controls = (index: number, open: boolean, onOpenChange: (open: boolean) => void) => ({
    open, onOpenChange, resizeLabel: t('resize'),
    onResizeStart: (event: React.PointerEvent<HTMLButtonElement>) => {
      if (event.button !== 0) return
      drag.current = { index, x: event.clientX, y: event.clientY, width: widths[index], height: index === 0 ? firstHeight : secondHeight }
      event.currentTarget.setPointerCapture(event.pointerId)
    },
    onResizeMove: (event: React.PointerEvent<HTMLButtonElement>) => {
      if (drag.current?.index === index) resize(index, drag.current.width + event.clientX - drag.current.x, drag.current.height + event.clientY - drag.current.y)
    },
    onResizeEnd: () => { drag.current = null },
    onResizeKey: (event: React.KeyboardEvent<HTMLButtonElement>) => {
      const offsets: Record<string, [number, number]> = { ArrowLeft: [-16, 0], ArrowRight: [16, 0], ArrowUp: [0, -16], ArrowDown: [0, 16] }
      const offset = offsets[event.key]
      if (!offset) return
      event.preventDefault()
      resize(index, widths[index] + offset[0], (index === 0 ? firstHeight : secondHeight) + offset[1])
    },
  })

  return (
    <div ref={container} className="flex h-[min(70dvh,40rem)] min-h-52 flex-col gap-4 overflow-y-auto lg:h-[calc(100dvh-3rem)] lg:min-h-0" aria-label={t('panels')}>
      <div className="max-w-full shrink-0" style={{ width: widths[0], height: projectsOpen ? firstHeight : undefined }}>
        <ProjectSelector {...controls(0, projectsOpen, setProjectsOpen)} />
      </div>
      <div className="max-w-full shrink-0" style={{ width: widths[1], height: assetsOpen ? secondHeight : undefined }}>
        <ProjectAssets {...controls(1, assetsOpen, setAssetsOpen)} />
      </div>
    </div>
  )
}
