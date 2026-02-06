'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Search, File, Image, Files, Images } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import type { AvailableVariable } from '../types'
import type { FileToUrlInput } from '../../nodes/file-to-url-node'

// 类型图标映射
const typeIcons: Record<string, React.ElementType> = {
  file: File,
  image: Image,
  files: Files,
  images: Images,
  File: File,
  Image: Image,
  Files: Files,
  Images: Images,
}

interface FileToUrlInputDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editingInput: FileToUrlInput | null
  existingInputs: FileToUrlInput[]
  variables: AvailableVariable[]  // 已过滤为文件类型
  variableSearch: string
  openVariablePopover: string | null
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
  onSave: (input: FileToUrlInput) => void
}

export function FileToUrlInputDialog({
  open,
  onOpenChange,
  editingInput,
  existingInputs,
  variables,
  variableSearch,
  openVariablePopover,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
  onSave,
}: FileToUrlInputDialogProps) {
  const t = useTranslations('workflow')
  const [form, setForm] = React.useState<Partial<FileToUrlInput>>({})

  React.useEffect(() => {
    if (open) {
      if (editingInput) {
        setForm({ ...editingInput })
      } else {
        setForm({ name: '', sourceVariable: '', sourceType: 'file' })
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

  // 根据变量类型推断源类型
  const inferSourceType = (varType: string): 'file' | 'image' | 'files' | 'images' => {
    const type = varType.toLowerCase()
    if (type === 'images') return 'images'
    if (type === 'files') return 'files'
    if (type === 'image') return 'image'
    return 'file'
  }

  const handleSave = () => {
    const name = form.name?.trim()
    const sourceVariable = form.sourceVariable
    if (!name || !sourceVariable) return
    if (!isValidVariableName(name)) return
    
    const input: FileToUrlInput = {
      id: editingInput?.id || `input_${Date.now()}`,
      name,
      sourceVariable,
      sourceType: form.sourceType || 'file',
    }
    
    onSave(input)
    onOpenChange(false)
  }

  const nameError = form.name && !isValidVariableName(form.name) ? t('dialogs.fileToUrlInput.nameFormatError') : null
  const duplicateError = form.name && existingInputs.some(
    i => i.id !== editingInput?.id && i.name === form.name
  ) ? t('dialogs.fileToUrlInput.nameDuplicate') : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-100 flex flex-col max-h-[85vh]">
        <DialogHeader>
          <DialogTitle className="text-sm">{editingInput ? t('dialogs.fileToUrlInput.editTitle') : t('dialogs.fileToUrlInput.addTitle')}</DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto py-2 px-1 -mx-1">
          <div className="space-y-4 px-0.5">
            {/* 选择文件变量 */}
            <div className="space-y-2">
              <Label className="text-xs">{t('dialogs.fileToUrlInput.selectFileVarLabel')}</Label>
              <Popover 
                open={openVariablePopover === 'file-to-url-source'}
                onOpenChange={(isOpen) => {
                  onOpenVariablePopoverChange(isOpen ? 'file-to-url-source' : null)
                  if (!isOpen) onVariableSearchChange('')
                }}
              >
                <PopoverTrigger
                  className="w-full h-9 flex items-center justify-start px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
                >
                  {form.sourceVariable ? (
                    <span className="flex items-center gap-1.5">
                      {(() => {
                        const Icon = typeIcons[form.sourceType || 'file'] || File
                        return <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                      })()}
                      <span className="text-xs font-mono">
                        {form.sourceVariable.replace(/\{\{|\}\}/g, '')}
                      </span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground text-xs">{t('dialogs.fileToUrlInput.selectFileVarPlaceholder')}</span>
                  )}
                </PopoverTrigger>
                <PopoverContent className="w-72 p-0" align="start">
                  <div className="p-2 border-b">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input
                        placeholder={t('dialogs.fileToUrlInput.searchPlaceholder')}
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
                              {variables.length === 0
                                ? t('dialogs.fileToUrlInput.noFileVarsAvailable')
                                : t('dialogs.fileToUrlInput.noMatch')
                              }
                            </div>
                          )
                        }
                        
                        return groupEntries.map(([groupId, group]) => (
                          <div key={groupId} className="mb-1">
                            <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                              {group.label}
                            </div>
                            {group.items.map(variable => {
                              const Icon = typeIcons[variable.type] || File
                              return (
                                <button
                                  key={variable.id}
                                  className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                                  onClick={() => {
                                    const sourceType = inferSourceType(variable.type)
                                    // 自动生成变量名（去掉前缀）
                                    const varName = variable.name.includes('.') 
                                      ? variable.name.split('.').pop() || variable.name
                                      : variable.name
                                    const outputName = `${varName}_url`
                                    
                                    setForm({
                                      ...form,
                                      sourceVariable: `{{${variable.name}}}`,
                                      sourceType,
                                      name: form.name || outputName,
                                    })
                                    onOpenVariablePopoverChange(null)
                                    onVariableSearchChange('')
                                  }}
                                >
                                  <span className="flex items-center gap-1.5">
                                    <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                                    <span className="font-mono">{variable.name}</span>
                                  </span>
                                  <span className="text-muted-foreground">{variable.type}</span>
                                </button>
                              )
                            })}
                          </div>
                        ))
                      })()}
                    </div>
                  </ScrollArea>
                </PopoverContent>
              </Popover>
            </div>

            {/* 输出变量名 */}
            <div className="space-y-2">
              <Label htmlFor="filetourlput-name" className="text-xs">{t('dialogs.fileToUrlInput.outputNameLabel')}</Label>
              <Input
                id="filetourlput-name"
                value={form.name || ''}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="例如: image_url, file_urls"
                className={cn(
                  'h-9 font-mono',
                  (nameError || duplicateError) && 'border-destructive! ring-destructive/20!'
                )}
              />
              {nameError && (
                <p className="text-[10px] text-destructive">{nameError}</p>
              )}
              {duplicateError && (
                <p className="text-[10px] text-destructive">{duplicateError}</p>
              )}
              <p className="text-[10px] text-muted-foreground">
                {t('dialogs.fileToUrlInput.outputTypePrefix')}{form.sourceType === 'files' || form.sourceType === 'images' ? 'string[] (URL 数组)' : 'string (URL)'}
              </p>
            </div>
          </div>
        </div>
        <DialogFooter className="shrink-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t('dialogs.fileToUrlInput.cancel')}
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!form.name?.trim() || !form.sourceVariable || !!nameError || !!duplicateError}
          >
            {editingInput ? t('dialogs.fileToUrlInput.save') : t('dialogs.fileToUrlInput.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
