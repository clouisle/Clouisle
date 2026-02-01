'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { PlusCircle, Check, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

export interface FilterOption {
  value: string
  label: string
  icon?: React.ReactNode
  count?: number
}

interface DataTableFacetedFilterProps {
  title: string
  options: FilterOption[]
  selectedValues: Set<string>
  onSelectionChange: (values: Set<string>) => void
  searchable?: boolean
}

export function DataTableFacetedFilter({
  title,
  options,
  selectedValues,
  onSelectionChange,
  searchable = false,
}: DataTableFacetedFilterProps) {
  const t = useTranslations('common')
  const [searchQuery, setSearchQuery] = React.useState('')
  const [open, setOpen] = React.useState(false)

  const filteredOptions = React.useMemo(() => {
    if (!searchQuery) return options
    return options.filter((option) =>
      option.label.toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [options, searchQuery])

  const toggleOption = (value: string) => {
    const newSelected = new Set(selectedValues)
    if (newSelected.has(value)) {
      newSelected.delete(value)
    } else {
      newSelected.add(value)
    }
    onSelectionChange(newSelected)
  }

  const clearFilters = () => {
    onSelectionChange(new Set())
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className={cn(
          "border-input hover:bg-accent hover:text-accent-foreground inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-md border border-dashed bg-transparent px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
          selectedValues.size > 0 && "border-solid"
        )}
      >
        <PlusCircle className="h-4 w-4" />
        {title}
        {selectedValues.size > 0 && (
          <>
            <Separator orientation="vertical" className="mx-1 h-4" />
            <div className="flex gap-1">
              {selectedValues.size > 2 ? (
                <Badge variant="secondary" className="rounded-sm px-1 font-normal">
                  {selectedValues.size} selected
                </Badge>
              ) : (
                Array.from(selectedValues).map((value) => {
                  const option = options.find((o) => o.value === value)
                  return (
                    <Badge
                      key={value}
                      variant="secondary"
                      className="rounded-sm px-1 font-normal"
                    >
                      {option?.label || value}
                    </Badge>
                  )
                })
              )}
            </div>
          </>
        )}
      </PopoverTrigger>
      <PopoverContent className="w-[200px] p-0" align="start">
        {searchable && (
          <div className="p-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={title}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 pl-8"
              />
            </div>
          </div>
        )}
        <div className="max-h-[300px] overflow-y-auto p-1">
          {filteredOptions.length === 0 ? (
            <div className="px-2 py-3 text-sm text-muted-foreground">
              {t('noResults')}
            </div>
          ) : (
            filteredOptions.map((option) => {
              const isSelected = selectedValues.has(option.value)
              return (
                <button
                  key={option.value}
                  onClick={() => toggleOption(option.value)}
                  className={cn(
                    "relative flex w-full cursor-pointer items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground",
                    isSelected && "bg-accent"
                  )}
                >
                  <div
                    className={cn(
                      "mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary",
                      isSelected
                        ? "bg-primary text-primary-foreground"
                        : "opacity-50 [&_svg]:invisible"
                    )}
                  >
                    <Check className="h-3 w-3" />
                  </div>
                  {option.icon && (
                    <span className="mr-2 text-muted-foreground">{option.icon}</span>
                  )}
                  <span className="flex-1 text-left">{option.label}</span>
                  {option.count !== undefined && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      {option.count}
                    </span>
                  )}
                </button>
              )
            })
          )}
        </div>
        {selectedValues.size > 0 && (
          <>
            <Separator />
            <div className="p-1">
              <button
                onClick={clearFilters}
                className="w-full rounded-sm px-2 py-1.5 text-center text-sm hover:bg-accent cursor-pointer"
              >
                {t('clearFilters')}
              </button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}
