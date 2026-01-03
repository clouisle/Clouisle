'use client'

import * as React from 'react'
import { X, ZoomIn, ZoomOut, RotateCw, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface ImageLightboxProps {
  src: string
  alt?: string
  isOpen: boolean
  onClose: () => void
}

export function ImageLightbox({ src, alt, isOpen, onClose }: ImageLightboxProps) {
  const [scale, setScale] = React.useState(1)
  const [rotation, setRotation] = React.useState(0)
  const [position, setPosition] = React.useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = React.useState(false)
  const [dragStart, setDragStart] = React.useState({ x: 0, y: 0 })
  const containerRef = React.useRef<HTMLDivElement>(null)

  // Reset state when closed
  React.useEffect(() => {
    if (!isOpen) {
      setScale(1)
      setRotation(0)
      setPosition({ x: 0, y: 0 })
    }
  }, [isOpen])

  // Handle escape key
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return
      
      switch (e.key) {
        case 'Escape':
          onClose()
          break
        case '+':
        case '=':
          handleZoomIn()
          break
        case '-':
          handleZoomOut()
          break
        case 'r':
          handleRotate()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Prevent body scroll when open
  React.useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])

  const handleZoomIn = () => {
    setScale((prev) => Math.min(prev + 0.25, 4))
  }

  const handleZoomOut = () => {
    setScale((prev) => Math.max(prev - 0.25, 0.5))
  }

  const handleRotate = () => {
    setRotation((prev) => (prev + 90) % 360)
  }

  const handleDownload = async () => {
    try {
      const response = await fetch(src)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = alt || 'image'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to download image:', err)
    }
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    if (scale > 1) {
      setIsDragging(true)
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y })
    }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging && scale > 1) {
      setPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      })
    }
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    setScale((prev) => Math.min(Math.max(prev + delta, 0.5), 4))
  }

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === containerRef.current) {
      onClose()
    }
  }

  if (!isOpen) return null

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm"
      onClick={handleBackdropClick}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {/* Controls */}
      <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-full bg-white/10 text-white hover:bg-white/20"
          onClick={handleZoomOut}
          title="缩小 (-)"
        >
          <ZoomOut className="h-5 w-5" />
        </Button>
        <span className="text-white text-sm min-w-15 text-center">
          {Math.round(scale * 100)}%
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-full bg-white/10 text-white hover:bg-white/20"
          onClick={handleZoomIn}
          title="放大 (+)"
        >
          <ZoomIn className="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-full bg-white/10 text-white hover:bg-white/20"
          onClick={handleRotate}
          title="旋转 (R)"
        >
          <RotateCw className="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-full bg-white/10 text-white hover:bg-white/20"
          onClick={handleDownload}
          title="下载"
        >
          <Download className="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-full bg-white/10 text-white hover:bg-white/20"
          onClick={onClose}
          title="关闭 (Esc)"
        >
          <X className="h-5 w-5" />
        </Button>
      </div>

      {/* Image */}
      <div
        className={cn(
          'relative max-w-[90vw] max-h-[90vh] select-none',
          scale > 1 ? 'cursor-grab' : 'cursor-zoom-in',
          isDragging && 'cursor-grabbing'
        )}
        onMouseDown={handleMouseDown}
        onWheel={handleWheel}
        onClick={(e) => {
          e.stopPropagation()
          if (scale === 1) handleZoomIn()
        }}
      >
        <img
          src={src}
          alt={alt || 'Preview'}
          className="max-w-full max-h-[90vh] object-contain transition-transform duration-200"
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${scale}) rotate(${rotation}deg)`,
            transformOrigin: 'center center',
          }}
          draggable={false}
        />
      </div>

      {/* Image info */}
      {alt && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-full bg-white/10 text-white text-sm">
          {alt}
        </div>
      )}
    </div>
  )
}

/**
 * Hook to manage lightbox state
 */
export function useLightbox() {
  const [isOpen, setIsOpen] = React.useState(false)
  const [imageSrc, setImageSrc] = React.useState('')
  const [imageAlt, setImageAlt] = React.useState<string | undefined>()

  const openLightbox = React.useCallback((src: string, alt?: string) => {
    setImageSrc(src)
    setImageAlt(alt)
    setIsOpen(true)
  }, [])

  const closeLightbox = React.useCallback(() => {
    setIsOpen(false)
  }, [])

  return {
    isOpen,
    imageSrc,
    imageAlt,
    openLightbox,
    closeLightbox,
  }
}
