'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import type { AvailableVariable } from '../types'
import type { CodeInput } from '../../nodes/code-node'

interface CodeInputDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editingInput: CodeInput | null
  existingInputs?: CodeInput[]
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
  onSave: (input: CodeInput) => void
}

export function CodeInputDialog({
  open,
  onOpenChange,
  editingInput,
  existingInputs = [],
  variables,
  variableSearch,
  openVariablePopover,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
  onSave,
}: CodeInputDialogProps) {
  const t = useTranslations('workflow')
  const [form, setForm] = React.useState<Partial<CodeInput>>({})

  React.useEffect(() => {
    if (open) {
      if (editingInput) {
        setForm({ ...editingInput })
      } else {
        setForm({ name: '', value: '' })
      }
    }
  }, [open, editingInput])

  // 过滤变量
  const filterVariables = (search: string) => {
    if (!search) return variables
    return variables.filter(v => 
      v.name.toLowerCase().includes(search.toLowerCase())
    )
  }

  // 分组变量
  const groupVariables = (vars: AvailableVariable[]) => {
    const groups = vars.reduce((acc, v) => {
      if (!acc[v.group]) {
        acc[v.group] = { label: v.groupLabel, isSystem: v.isSystem, items: [] }
      }
      acc[v.group].items.push(v)
      return acc
    }, {} as Record<string, { label: string; isSystem: boolean; items: AvailableVariable[] }>)
    
    const entries = Object.entries(groups)
    entries.sort((a, b) => {
      if (a[1].isSystem && !b[1].isSystem) return 1
      if (!a[1].isSystem && b[1].isSystem) return -1
      return 0
    })
    
    return entries
  }

  const trimmedName = form.name?.trim() || ''
  const isDuplicateName = trimmedName !== '' && existingInputs.some(
    (i) => i.name === trimmedName && i.id !== editingInput?.id
  )

  const handleSave = () => {
    const name = trimmedName
    const value = form.value
    if (!name || !value) return
    if (!isValidVariableName(name)) return
    if (isDuplicateName) return

    const input: CodeInput = {
      id: editingInput?.id || `input_${Date.now()}`,
      name,
      value,
      valueSource: form.valueSource,
    }

    onSave(input)
    onOpenChange(false)
  }

  const nameError = form.name && !isValidVariableName(form.name)
    ? t('dialogs.codeInput.nameFormatError')
    : isDuplicateName
      ? t('dialogs.codeInput.duplicateNameError')
      : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-100 flex flex-col max-h-[85vh]">
        <DialogHeader>
          <DialogTitle className="text-sm">{editingInput ? t('dialogs.codeInput.editTitle') : t('dialogs.codeInput.addTitle')}</DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto py-2 px-1 -mx-1">
          <div className="space-y-4 px-0.5">
            <div className="space-y-2">
              <Label htmlFor="codeinput-name" className="text-xs">{t('dialogs.codeInput.nameLabel')}</Label>
              <Input
                id="codeinput-name"
                value={form.name || ''}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={t('dialogs.codeInput.namePlaceholder')}
                className={cn(
                  'h-9 font-mono',
                  nameError && 'border-destructive! ring-destructive/20!'
                )}
              />
              {nameError && (
                <p className="text-[10px] text-destructive">{nameError}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label className="text-xs">{t('dialogs.codeInput.valueLabel')}</Label>
              <Popover 
                open={openVariablePopover === 'code-input-value'}
                onOpenChange={(isOpen) => {
                  onOpenVariablePopoverChange(isOpen ? 'code-input-value' : null)
                  if (!isOpen) onVariableSearchChange('')
                }}
              >
                <PopoverTrigger
                  className="w-full h-9 flex items-center justify-start px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
                >
                  {form.value ? (
                    <span className="flex items-center gap-1">
                      <span className="text-primary/80 font-mono text-xs">{'{x}'}</span>
                      <span className="text-xs">
                        {form.valueSource && <span className="text-muted-foreground">{form.valueSource} / </span>}
                        {form.value.replace(/\{\{|\}\}/g, '').split('.').pop()}
                      </span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground text-xs">{t('dialogs.codeInput.selectUpstreamPlaceholder')}</span>
                  )}
                </PopoverTrigger>
                <PopoverContent className="w-72 p-0" align="start">
                  <div className="p-2 border-b">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input
                        placeholder={t('dialogs.codeInput.searchPlaceholder')}
                        value={variableSearch}
                        onChange={(e) => onVariableSearchChange(e.target.value)}
                        className="h-8 pl-8 text-xs"
                      />
                    </div>
                  </div>
                  <ScrollArea className="h-50">
                    <div className="p-1">
                      {(() => {
                        const filtered = filterVariables(variableSearch)
                        const groupEntries = groupVariables(filtered)
                        
                        if (groupEntries.length === 0) {
                          return (
                            <div className="py-4 text-center text-xs text-muted-foreground">
                              {t('dialogs.codeInput.noMatch')}
                            </div>
                          )
                        }
                        
                        return groupEntries.map(([groupId, group]) => (
                          <div key={groupId} className="mb-1">
                            <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                              {group.label}
                            </div>
                            {group.items.map(variable => (
                              <button
                                key={variable.id}
                                className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                                onClick={() => {
                                  setForm({
                                    ...form,
                                    value: `{{${variable.id}}}`,
                                    valueSource: variable.isSystem ? t('nodesCommon.system') : variable.groupLabel
                                  })
                                  onOpenVariablePopoverChange(null)
                                  onVariableSearchChange('')
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
                      })()}
                    </div>
                  </ScrollArea>
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </div>
        <DialogFooter className="shrink-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t('dialogs.codeInput.cancel')}
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!form.name?.trim() || !form.value || !!nameError || isDuplicateName}
          >
            {editingInput ? t('dialogs.codeInput.save') : t('dialogs.codeInput.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
