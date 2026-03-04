'use client'

import {
  Search,
  ZoomIn,
  ZoomOut,
  Maximize,
} from 'lucide-react'
import { useTranslations } from 'next-intl'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface GraphToolbarProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  onZoomIn: () => void
  onZoomOut: () => void
  onFitView: () => void
  entityCount: number
  relationCount: number
}

export function GraphToolbar({
  searchQuery,
  onSearchChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  entityCount,
  relationCount,
}: GraphToolbarProps) {
  const t = useTranslations('memories')

  return (
    <div className="bg-background border rounded-lg shadow-lg p-2 space-y-2">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={t('searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-8 h-8"
        />
      </div>

      {/* Zoom Controls */}
      <div className="flex gap-1">
        <Button size="sm" variant="outline" onClick={onZoomIn}>
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button size="sm" variant="outline" onClick={onZoomOut}>
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button size="sm" variant="outline" onClick={onFitView}>
          <Maximize className="h-4 w-4" />
        </Button>
      </div>

      {/* Stats */}
      <div className="text-xs text-muted-foreground">
        {entityCount} {t('entities')} · {relationCount} {t('relations')}
      </div>
    </div>
  )
}
