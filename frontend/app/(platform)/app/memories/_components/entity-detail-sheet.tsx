'use client'

import { useTranslations } from 'next-intl'

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
import { formatDateTime } from '@/lib/utils'

interface EntityDetailSheetProps {
  entity: MemoryEntity | null
  entities: MemoryEntity[]
  relations: MemoryRelation[]
  onClose: () => void
  onNavigateToEntity: (entityId: string) => void
}

export function EntityDetailSheet({
  entity,
  entities,
  relations,
  onClose,
  onNavigateToEntity,
}: EntityDetailSheetProps) {
  const t = useTranslations('memories')

  if (!entity) return null

  // Create entity lookup map
  const entityMap = new Map(entities.map((e) => [e.id, e]))

  const outgoingRelations = relations.filter(
    (rel) => rel.source_entity_id === entity.id
  )
  const incomingRelations = relations.filter(
    (rel) => rel.target_entity_id === entity.id
  )

  const getEntityName = (entityId: string) => {
    return entityMap.get(entityId)?.name || 'Unknown'
  }

  return (
    <Sheet open={!!entity} onOpenChange={() => onClose()}>
      <SheetContent className="w-[400px] sm:w-[500px] flex flex-col px-6">
        <div className="flex-1 overflow-y-auto space-y-6 mt-6 pb-6 -mx-6 px-6">
          {/* Entity Name */}
          <div className="space-y-3">
            <h2 className="text-xl font-semibold">{entity.name}</h2>
            <Badge variant="secondary">{t(`entityTypes.${entity.entity_type}`)}</Badge>
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
                <h4 className="text-sm font-semibold">
                  {t('properties')}
                </h4>
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
              <h4 className="text-sm font-semibold">
                {t('outgoingRelations')}
              </h4>
              <div className="space-y-2">
                {outgoingRelations.map((rel) => (
                  <Button
                    key={rel.id}
                    variant="outline"
                    size="sm"
                    className="w-full justify-start text-left h-auto py-3 px-3"
                    onClick={() => onNavigateToEntity(rel.target_entity_id)}
                  >
                    <span className="text-xs leading-relaxed">
                      <span className="text-muted-foreground">{getEntityName(rel.source_entity_id)}</span>
                      {' → '}
                      <span className="font-semibold text-primary">
                        {t(`relationTypes.${rel.relation_type}`)}
                      </span>
                      {' → '}
                      <span className="font-medium">{getEntityName(rel.target_entity_id)}</span>
                    </span>
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Incoming Relations */}
          {incomingRelations.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold">
                {t('incomingRelations')}
              </h4>
              <div className="space-y-2">
                {incomingRelations.map((rel) => (
                  <Button
                    key={rel.id}
                    variant="outline"
                    size="sm"
                    className="w-full justify-start text-left h-auto py-3 px-3"
                    onClick={() => onNavigateToEntity(rel.source_entity_id)}
                  >
                    <span className="text-xs leading-relaxed">
                      <span className="font-medium">{getEntityName(rel.source_entity_id)}</span>
                      {' → '}
                      <span className="font-semibold text-primary">
                        {t(`relationTypes.${rel.relation_type}`)}
                      </span>
                      {' → '}
                      <span className="text-muted-foreground">{getEntityName(rel.target_entity_id)}</span>
                    </span>
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Metadata - Fixed at bottom */}
        <div className="pt-4 mt-4 bg-background">
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
        </div>
      </SheetContent>
    </Sheet>
  )
}
