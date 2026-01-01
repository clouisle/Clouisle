'use client'

import * as React from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { AvailableVariable } from './types'

interface VariableSelectorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  variables: AvailableVariable[]
  selectedValue?: string
  placeholder?: string
  onSelect: (variable: AvailableVariable) => void
  filterType?: 'iterable' | 'all'
  triggerClassName?: string
}

export function VariableSelector({
  open,
  onOpenChange,
  variables,
  selectedValue,
  placeholder = '选择变量...',
  onSelect,
  triggerClassName,
}: VariableSelectorProps) {
  const [search, setSearch] = React.useState('')

  const filteredVariables = React.useMemo(() => {
    if (!search) return variables
    return variables.filter(v => 
      v.name.toLowerCase().includes(search.toLowerCase())
    )
  }, [variables, search])

  // 按 group 分组
  const groupedVariables = React.useMemo(() => {
    const groups = filteredVariables.reduce((acc, v) => {
      if (!acc[v.group]) {
        acc[v.group] = { label: v.groupLabel, isSystem: v.isSystem, items: [] }
      }
      acc[v.group].items.push(v)
      return acc
    }, {} as Record<string, { label: string; isSystem: boolean; items: AvailableVariable[] }>)
    
    // 非系统组在前，系统组在后
    const entries = Object.entries(groups)
    entries.sort((a, b) => {
      if (a[1].isSystem && !b[1].isSystem) return 1
      if (!a[1].isSystem && b[1].isSystem) return -1
      return 0
    })
    
    return entries
  }, [filteredVariables])

  return (
    <Popover 
      open={open} 
      onOpenChange={(isOpen) => {
        onOpenChange(isOpen)
        if (!isOpen) setSearch('')
      }}
    >
      <PopoverTrigger
        className={cn(
          "w-full h-9 flex items-center justify-start px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground",
          triggerClassName
        )}
      >
        {selectedValue ? (
          <span className="flex items-center gap-1">
            <span className="text-primary/80 font-mono text-xs">{'{x}'}</span>
            <span className="text-xs">{selectedValue.replace(/\{\{|\}\}/g, '')}</span>
          </span>
        ) : (
          <span className="text-muted-foreground text-xs">{placeholder}</span>
        )}
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        {/* 搜索框 */}
        <div className="p-2 border-b">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="搜索变量"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 pl-8 text-xs"
            />
          </div>
        </div>
        {/* 变量列表 */}
        <ScrollArea className="h-50">
          <div className="p-1">
            {groupedVariables.length === 0 ? (
              <div className="py-4 text-center text-xs text-muted-foreground">
                未找到匹配的变量
              </div>
            ) : (
              groupedVariables.map(([groupId, group]) => (
                <div key={groupId} className="mb-1">
                  <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                    {group.label}
                  </div>
                  {group.items.map(variable => (
                    <button
                      key={variable.id}
                      className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                      onClick={() => {
                        onSelect(variable)
                        onOpenChange(false)
                        setSearch('')
                      }}
                    >
                      <span className="flex items-center gap-1.5">
                        <span className={cn(
                          'font-mono',
                          variable.isSystem ? 'text-orange-500' : 'text-primary/80'
                        )}>{'{x}'}</span>
                        <span>{variable.name}</span>
                      </span>
                      <span className="text-muted-foreground">{variable.type}</span>
                    </button>
                  ))}
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
