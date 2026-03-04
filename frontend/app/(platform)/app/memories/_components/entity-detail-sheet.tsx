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
      <SheetContent className="w-[400px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{entity.name}</SheetTitle>
          <SheetDescription>
            <Badge>{t(`entityTypes.${entity.entity_type}`)}</Badge>
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-4 mt-4">
          {/* Description */}
          {entity.description && (
            <div>
              <h4 className="text-sm font-medium mb-1">{t('description')}</h4>
              <p className="text-sm text-muted-foreground">
                {entity.description}
              </p>
            </div>
          )}

          {/* Properties */}
          {entity.properties &&
            Object.keys(entity.properties).length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-1">
                  {t('properties')}
                </h4>
                <div className="space-y-1">
                  {Object.entries(entity.properties).map(([key, value]) => (
                    <div key={key} className="text-sm">
                      <span className="font-medium">{key}:</span>{' '}
                      {String(value)}
                    </div>
                  ))}
                </div>
              </div>
            )}

          {/* Outgoing Relations */}
          {outgoingRelations.length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2">
                {t('outgoingRelations')}
              </h4>
              <div className="space-y-1">
                {outgoingRelations.map((rel) => (
                  <Button
                    key={rel.id}
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start text-left h-auto py-2"
                    onClick={() => onNavigateToEntity(rel.target_entity_id)}
                  >
                    <span className="text-xs">
                      {getEntityName(rel.source_entity_id)} →{' '}
                      <span className="font-medium">
                        {t(`relationTypes.${rel.relation_type}`)}
                      </span>{' '}
                      → {getEntityName(rel.target_entity_id)}
                    </span>
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Incoming Relations */}
          {incomingRelations.length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2">
                {t('incomingRelations')}
              </h4>
              <div className="space-y-1">
                {incomingRelations.map((rel) => (
                  <Button
                    key={rel.id}
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start text-left h-auto py-2"
                    onClick={() => onNavigateToEntity(rel.source_entity_id)}
                  >
                    <span className="text-xs">
                      {getEntityName(rel.source_entity_id)} →{' '}
                      <span className="font-medium">
                        {t(`relationTypes.${rel.relation_type}`)}
                      </span>{' '}
                      → {getEntityName(rel.target_entity_id)}
                    </span>
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="text-xs text-muted-foreground space-y-1 pt-4 border-t">
            <div>
              {t('accessCount')}: {entity.access_count}
            </div>
            {entity.last_accessed_at && (
              <div>
                {t('lastAccessed')}: {formatDateTime(entity.last_accessed_at)}
              </div>
            )}
            <div>
              {t('createdAt')}: {formatDateTime(entity.created_at)}
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
