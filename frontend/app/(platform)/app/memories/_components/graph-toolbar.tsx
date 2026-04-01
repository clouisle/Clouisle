'use client'

import {
  Search,
  ZoomIn,
  ZoomOut,
  Maximize,
  MousePointer2,
  Trash2,
} from 'lucide-react'
import { useTranslations } from 'next-intl'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface GraphToolbarProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  onZoomIn: () => void
  onZoomOut: () => void
  onFitView: () => void
  entityCount: number
  relationCount: number
  selectMode: boolean
  onToggleSelectMode: () => void
  selectedCount?: number
  onDeleteSelected?: () => void
}

export function GraphToolbar({
  searchQuery,
  onSearchChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  entityCount,
  relationCount,
  selectMode,
  onToggleSelectMode,
  selectedCount = 0,
  onDeleteSelected,
}: GraphToolbarProps) {
  const t = useTranslations('memories')

  return (
    <TooltipProvider>
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
          <Tooltip>
            <TooltipTrigger
              onClick={onZoomIn}
              render={
                <Button size="sm" variant="outline">
                  <ZoomIn className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent side="bottom">{t('zoomIn')}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              onClick={onZoomOut}
              render={
                <Button size="sm" variant="outline">
                  <ZoomOut className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent side="bottom">{t('zoomOut')}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              onClick={onFitView}
              render={
                <Button size="sm" variant="outline">
                  <Maximize className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent side="bottom">{t('fitView')}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              onClick={onToggleSelectMode}
              render={
                <Button size="sm" variant={selectMode ? 'default' : 'outline'}>
                  <MousePointer2 className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent side="bottom">{t('selectMode')}</TooltipContent>
          </Tooltip>
        </div>

        {/* Stats */}
        <div className="text-xs text-muted-foreground">
          {entityCount} {t('entities')} · {relationCount} {t('relations')}
        </div>

        {/* Batch Delete */}
        {selectedCount > 0 && (
          <AlertDialog>
            <AlertDialogTrigger
              render={
                <Button size="sm" variant="destructive" className="w-full cursor-pointer">
                  <Trash2 className="h-4 w-4 mr-1" />
                  {t('deleteSelected')} ({selectedCount})
                </Button>
              }
            />
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('deleteSelected')}</AlertDialogTitle>
                <AlertDialogDescription>
                  {t('deleteSelectedConfirm', { count: selectedCount })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction onClick={onDeleteSelected}>
                  {t('delete')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </TooltipProvider>
  )
}
