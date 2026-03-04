'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { memoriesApi, type MemoryEntity } from '@/lib/api/admin/memories'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'
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
import { useCanPerform } from '@/components/permission-guard'

interface EntityDialogProps {
  entity: MemoryEntity | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function EntityDialog({ entity, open, onOpenChange, onSuccess }: EntityDialogProps) {
  const t = useTranslations('memories')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()

  const [isLoading, setIsLoading] = React.useState(false)
  const [fullEntity, setFullEntity] = React.useState<MemoryEntity | null>(null)
  const [description, setDescription] = React.useState('')
  const [properties, setProperties] = React.useState('')
  const [deleteRelationId, setDeleteRelationId] = React.useState<string | null>(null)

  // Load full entity details
  React.useEffect(() => {
    if (entity && open) {
      const loadEntity = async () => {
        try {
          const data = await memoriesApi.getEntity(entity.id)
          setFullEntity(data)
          setDescription(data.description || '')
          setProperties(JSON.stringify(data.properties, null, 2))
        } catch {
          // Error handled by API client
        }
      }
      loadEntity()
    }
  }, [entity, open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!entity) return

    setIsLoading(true)
    try {
      // Parse properties JSON
      let parsedProperties = {}
      if (properties.trim()) {
        try {
          parsedProperties = JSON.parse(properties)
        } catch {
          toast.error(commonT('invalidJSON'))
          setIsLoading(false)
          return
        }
      }

      await memoriesApi.updateEntity(entity.id, {
        description: description || undefined,
        properties: parsedProperties,
      })

      toast.success(t('editEntity'))
      onSuccess()
    } catch {
      // Error handled by API client
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteRelation = async (relationId: string) => {
    try {
      await memoriesApi.deleteRelation(relationId)
      toast.success(commonT('deleteSuccess'))
      setDeleteRelationId(null)

      // Reload entity
      if (entity) {
        const data = await memoriesApi.getEntity(entity.id)
        setFullEntity(data)
      }
    } catch {
      // Error handled by API client
    }
  }

  const getTypeBadgeColor = (type: string) => {
    const colors: Record<string, string> = {
      person: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
      preference: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
      skill: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
      project: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
      goal: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
      fact: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
      concept: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300',
      organization: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-300',
      location: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300',
      custom: 'bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-300',
    }
    return colors[type] || colors.custom
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('editEntity')}</DialogTitle>
            <DialogDescription>
              {t('description')}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Read-only info */}
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <Avatar className="h-10 w-10">
                  <AvatarImage src={entity?.user_avatar_url || undefined} />
                  <AvatarFallback>
                    {entity?.user_name.slice(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <div className="text-sm font-medium">{entity?.user_name}</div>
                  <div className="text-xs text-muted-foreground">{t('user')}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-muted-foreground mb-1">{t('entityName')}</div>
                  <div className="text-sm font-medium">{entity?.name}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">{t('entityType')}</div>
                  <Badge className={getTypeBadgeColor(entity?.entity_type || '')}>
                    {entity && t(`types.${entity.entity_type}`)}
                  </Badge>
                </div>
              </div>
            </div>

            <Separator />

            {/* Editable fields */}
            <div className="space-y-2">
              <Label htmlFor="description">{t('description')}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('noDescription')}
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="properties">{t('properties')}</Label>
              <Textarea
                id="properties"
                value={properties}
                onChange={(e) => setProperties(e.target.value)}
                placeholder="{}"
                rows={5}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                JSON format
              </p>
            </div>

            {/* Relations */}
            {fullEntity && (
              <>
                <Separator />

                <div className="space-y-3">
                  <div>
                    <h4 className="text-sm font-medium mb-2">{t('outgoingRelations')}</h4>
                    {fullEntity.outgoing_relations && fullEntity.outgoing_relations.length > 0 ? (
                      <div className="space-y-2">
                        {fullEntity.outgoing_relations.map((rel) => (
                          <div
                            key={rel.id}
                            className="flex items-center justify-between rounded-md border p-2 text-sm"
                          >
                            <div className="flex-1">
                              <span className="font-medium">{rel.target_entity_name}</span>
                              <Badge variant="outline" className="ml-2">
                                {t(`relationTypes.${rel.relation_type}`)}
                              </Badge>
                              {rel.description && (
                                <p className="text-xs text-muted-foreground mt-1">
                                  {rel.description}
                                </p>
                              )}
                            </div>
                            {canPerform('memory:delete') && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => setDeleteRelationId(rel.id)}
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">{t('noRelations')}</p>
                    )}
                  </div>

                  <div>
                    <h4 className="text-sm font-medium mb-2">{t('incomingRelations')}</h4>
                    {fullEntity.incoming_relations && fullEntity.incoming_relations.length > 0 ? (
                      <div className="space-y-2">
                        {fullEntity.incoming_relations.map((rel) => (
                          <div
                            key={rel.id}
                            className="flex items-center justify-between rounded-md border p-2 text-sm"
                          >
                            <div className="flex-1">
                              <span className="font-medium">{rel.source_entity_name}</span>
                              <Badge variant="outline" className="ml-2">
                                {t(`relationTypes.${rel.relation_type}`)}
                              </Badge>
                              {rel.description && (
                                <p className="text-xs text-muted-foreground mt-1">
                                  {rel.description}
                                </p>
                              )}
                            </div>
                            {canPerform('memory:delete') && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => setDeleteRelationId(rel.id)}
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">{t('noRelations')}</p>
                    )}
                  </div>
                </div>
              </>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isLoading}
              >
                {commonT('cancel')}
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {commonT('save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete relation confirmation */}
      <AlertDialog open={!!deleteRelationId} onOpenChange={() => setDeleteRelationId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{commonT('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {commonT('deleteWarning')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deleteRelationId && handleDeleteRelation(deleteRelationId)}
            >
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
