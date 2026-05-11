'use client'

import { useTranslations } from 'next-intl'

import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'

interface GraphFiltersProps {
  availableEntityTypes: string[]
  availableRelationTypes: string[]
  entityTypeFilter: string[]
  onEntityTypeFilterChange: (types: string[]) => void
  relationTypeFilter: string[]
  onRelationTypeFilterChange: (types: string[]) => void
}

export function GraphFilters({
  availableEntityTypes,
  availableRelationTypes,
  entityTypeFilter,
  onEntityTypeFilterChange,
  relationTypeFilter,
  onRelationTypeFilterChange,
}: GraphFiltersProps) {
  const t = useTranslations('memories')

  const getEntityTypeLabel = (entityType: string) => {
    const key = `entityTypes.${entityType}`
    return t.has(key) ? t(key) : entityType
  }

  const getRelationTypeLabel = (relationType: string) => {
    const key = `relationTypes.${relationType}`
    return t.has(key) ? t(key) : relationType
  }

  return (
    <div className="bg-background border rounded-lg shadow-lg p-3 space-y-3 max-w-[250px]">
      <div>
        <h4 className="text-sm font-medium mb-2">{t('entityTypesLabel')}</h4>
        <div className="space-y-1 max-h-[200px] overflow-y-auto">
          {availableEntityTypes.map((type) => (
            <label
              key={type}
              className="flex items-center gap-2 text-sm cursor-pointer"
            >
              <Checkbox
                checked={entityTypeFilter.includes(type)}
                onCheckedChange={(checked) => {
                  if (checked) {
                    onEntityTypeFilterChange([...entityTypeFilter, type])
                  } else {
                    onEntityTypeFilterChange(
                      entityTypeFilter.filter((t) => t !== type)
                    )
                  }
                }}
              />
              <span>{getEntityTypeLabel(type)}</span>
            </label>
          ))}
        </div>
      </div>

      <Separator />

      <div>
        <h4 className="text-sm font-medium mb-2">{t('relationTypesLabel')}</h4>
        <div className="space-y-1 max-h-[200px] overflow-y-auto">
          {availableRelationTypes.map((type) => (
            <label
              key={type}
              className="flex items-center gap-2 text-sm cursor-pointer"
            >
              <Checkbox
                checked={relationTypeFilter.includes(type)}
                onCheckedChange={(checked) => {
                  if (checked) {
                    onRelationTypeFilterChange([...relationTypeFilter, type])
                  } else {
                    onRelationTypeFilterChange(
                      relationTypeFilter.filter((t) => t !== type)
                    )
                  }
                }}
              />
              <span>{getRelationTypeLabel(type)}</span>
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
