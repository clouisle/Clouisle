'use client'

import { useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import type { MemoryEntity, MemoryRelation } from '@/lib/api/memories'
import { memoriesApi } from '@/lib/api/memories'
import { formatDateTime } from '@/lib/utils'

interface EntityDetailSheetProps {
  entity: MemoryEntity | null
  entities: MemoryEntity[]
  relations: MemoryRelation[]
  onClose: () => void
  onNavigateToEntity: (entityId: string) => void
  onDeleteEntity?: (entityId: string) => void
  onDeleteRelation?: (relationId: string) => void
}

export function EntityDetailSheet({
  entity,
  entities,
  relations,
  onClose,
  onNavigateToEntity,
  onDeleteEntity,
  onDeleteRelation,
}: EntityDetailSheetProps) {
  const t = useTranslations('memories')
  const [deleteEntityOpen, setDeleteEntityOpen] = useState(false)
  const [deleteRelationId, setDeleteRelationId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  if (!entity) return null

  const entityMap = new Map(entities.map((e) => [e.id, e]))

  const outgoingRelations = relations.filter(
    (rel) => rel.source_entity_id === entity.id
  )
  const incomingRelations = relations.filter(
    (rel) => rel.target_entity_id === entity.id
  )

  const getEntityName = (entityId: string) => {
    return entityMap.get(entityId)?.name || t('unknown')
  }

  const handleDeleteEntity = async () => {
    setDeleting(true)
    try {
      await memoriesApi.deleteEntity(entity.id)
      toast.success(t('deleteEntitySuccess'))
      onDeleteEntity?.(entity.id)
      onClose()
    } catch {
      // error toast handled by interceptor
    } finally {
      setDeleting(false)
      setDeleteEntityOpen(false)
    }
  }

  const handleDeleteRelation = async () => {
    if (!deleteRelationId) return
    setDeleting(true)
    try {
      await memoriesApi.deleteRelation(deleteRelationId)
      toast.success(t('deleteRelationSuccess'))
      onDeleteRelation?.(deleteRelationId)
    } catch {
      // error toast handled by interceptor
    } finally {
      setDeleting(false)
      setDeleteRelationId(null)
    }
  }

  const getEntityTypeLabel = (entityType: string) => {
    const key = `entityTypes.${entityType}`
    return t.has(key) ? t(key) : entityType
  }

  const getRelationTypeLabel = (relationType: string) => {
    const key = `relationTypes.${relationType}`
    return t.has(key) ? t(key) : relationType
  }

  const renderRelationItem = (rel: MemoryRelation, navigateToId: string) => (
    <div key={rel.id} className="flex items-center gap-1">
      <Button
        variant="outline"
        size="sm"
        className="flex-1 justify-start text-left h-auto py-3 px-3"
        onClick={() => onNavigateToEntity(navigateToId)}
      >
        <div className="flex flex-col gap-1">
          <span className="text-xs leading-relaxed">
            <span className="text-muted-foreground">{getEntityName(rel.source_entity_id)}</span>
            {' → '}
            <span className="font-semibold text-primary">
              {getRelationTypeLabel(rel.relation_type)}
            </span>
            {' → '}
            <span className="font-medium">{getEntityName(rel.target_entity_id)}</span>
          </span>
          {rel.description && (
            <span className="text-xs text-muted-foreground">{rel.description}</span>
          )}
        </div>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive cursor-pointer"
        onClick={(e) => {
          e.stopPropagation()
          setDeleteRelationId(rel.id)
        }}
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
  return (
    <>
      <Sheet open={!!entity} onOpenChange={() => onClose()}>
        <SheetContent className="w-[400px] sm:w-[500px] flex flex-col px-6">
          <SheetHeader className="sr-only">
            <SheetTitle>{t('detailTitle')}</SheetTitle>
            <SheetDescription>{entity.name}</SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto space-y-6 mt-6 pb-6 -mx-6 px-6">
            {/* Entity Name */}
            <div className="space-y-3">
              <h2 className="text-xl font-semibold pr-8">{entity.name}</h2>
              <Badge variant="secondary">{getEntityTypeLabel(entity.entity_type)}</Badge>
            </div>

            {/* Description */}
            {entity.description && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold">{t('description')}</h4>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {entity.description}
                </p>
              </div>
            )}

            {/* Properties */}
            {entity.properties &&
              Object.keys(entity.properties).length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold">{t('properties')}</h4>
                  <div className="space-y-2 rounded-lg border p-3 bg-muted/30">
                    {Object.entries(entity.properties).map(([key, value]) => (
                      <div key={key} className="text-sm flex gap-2">
                        <span className="font-medium text-foreground min-w-[80px]">{key}:</span>
                        <span className="text-muted-foreground flex-1">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            {/* Outgoing Relations */}
            {outgoingRelations.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold">{t('outgoingRelations')}</h4>
                <div className="space-y-2">
                  {outgoingRelations.map((rel) =>
                    renderRelationItem(rel, rel.target_entity_id)
                  )}
                </div>
              </div>
            )}

            {/* Incoming Relations */}
            {incomingRelations.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold">{t('incomingRelations')}</h4>
                <div className="space-y-2">
                  {incomingRelations.map((rel) =>
                    renderRelationItem(rel, rel.source_entity_id)
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Metadata + Delete - Fixed at bottom */}
          <div className="pt-4 mt-4 pb-4 bg-background space-y-4">
            <div className="text-xs text-muted-foreground space-y-2">
              <div className="flex justify-between">
                <span>{t('accessCount')}:</span>
                <span className="font-medium">{entity.access_count}</span>
              </div>
              {entity.last_accessed_at && (
                <div className="flex justify-between">
                  <span>{t('lastAccessed')}:</span>
                  <span className="font-medium">{formatDateTime(entity.last_accessed_at)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span>{t('createdAt')}:</span>
                <span className="font-medium">{formatDateTime(entity.created_at)}</span>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full text-destructive hover:text-destructive hover:bg-destructive/10 cursor-pointer"
              onClick={() => setDeleteEntityOpen(true)}
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              {t('deleteEntity')}
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      {/* Delete Entity Confirmation */}
      <AlertDialog open={deleteEntityOpen} onOpenChange={setDeleteEntityOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteEntity')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteEntity} disabled={deleting}>
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Relation Confirmation */}
      <AlertDialog open={!!deleteRelationId} onOpenChange={(open) => !open && setDeleteRelationId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteRelation')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteRelationConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteRelation} disabled={deleting}>
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
