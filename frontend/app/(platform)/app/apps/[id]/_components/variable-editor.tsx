'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Type,
  AlignLeft,
  ChevronDown,
  Hash,
  CheckSquare,
  Trash2,
  Plus,
  Pencil,
  X,
} from 'lucide-react'
import { type VariableDefinition, type VariableType } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const variableTypes: { value: VariableType; labelKey: string; icon: React.ElementType }[] = [
  { value: 'text', labelKey: 'text', icon: Type },
  { value: 'paragraph', labelKey: 'paragraph', icon: AlignLeft },
  { value: 'select', labelKey: 'select', icon: ChevronDown },
  { value: 'number', labelKey: 'number', icon: Hash },
  { value: 'checkbox', labelKey: 'checkbox', icon: CheckSquare },
]

const typeToDataType: Record<VariableType, string> = {
  text: 'string',
  paragraph: 'string',
  select: 'string',
  number: 'number',
  checkbox: 'boolean',
}

function getTypeIcon(type: VariableType) {
  return variableTypes.find((t) => t.value === type)?.icon || Type
}

function getTypeLabelKey(type: VariableType) {
  return variableTypes.find((t) => t.value === type)?.labelKey || type
}

interface AddVariableButtonProps {
  onAdd: (type: VariableType) => void
}

export function AddVariableButton({ onAdd }: AddVariableButtonProps) {
  const t = useTranslations('agents.orchestration.variables')
  const [open, setOpen] = React.useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 cursor-pointer">
            <Plus className="h-3 w-3" />
            {t('add')}
          </Button>
        }
      />
      <PopoverContent className="w-32 p-1" align="end">
        {variableTypes.map((type) => (
          <button
            key={type.value}
            className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted transition-colors text-left text-sm"
            onClick={() => {
              onAdd(type.value)
              setOpen(false)
            }}
          >
            <type.icon className="h-3.5 w-3.5 text-muted-foreground" />
            {t(`types.${type.labelKey}`)}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

interface VariableEditDialogProps {
  variable: VariableDefinition
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (variable: VariableDefinition) => void
  onCancel: () => void
}

function VariableEditDialog({ variable, open, onOpenChange, onSave, onCancel }: VariableEditDialogProps) {
  const t = useTranslations('agents.orchestration.variables')
  const [draft, setDraft] = React.useState<VariableDefinition>(variable)
  const TypeIcon = getTypeIcon(draft.type)

  React.useEffect(() => {
    setDraft(variable)
  }, [variable])

  const updateField = <K extends keyof VariableDefinition>(key: K, value: VariableDefinition[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = () => {
    onSave(draft)
  }

  const handleCancel = () => {
    onCancel()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('dialog.title')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label className="text-sm text-muted-foreground">{t('dialog.fieldType')}</Label>
            <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
              <TypeIcon className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">{t(`types.${getTypeLabelKey(draft.type)}`)}</span>
              <div className="ml-auto">
                <Select value={typeToDataType[draft.type]} disabled>
                  <SelectTrigger className="h-7 w-20 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="string">string</SelectItem>
                    <SelectItem value="number">number</SelectItem>
                    <SelectItem value="boolean">boolean</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-sm">{t('dialog.variableName')}</Label>
            <Input
              value={draft.name}
              onChange={(e) => updateField('name', e.target.value.replace(/\s/g, '_'))}
              placeholder="name"
              className="font-mono"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-sm">{t('dialog.displayName')}</Label>
            <Input
              value={draft.label || ''}
              onChange={(e) => updateField('label', e.target.value || null)}
              placeholder={t('dialog.displayNamePlaceholder')}
            />
          </div>

          {draft.type === 'select' && (
            <div className="space-y-2">
              <Label className="text-sm">{t('dialog.options')}</Label>
              <div className="space-y-2">
                {(draft.options || []).map((option, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      value={option}
                      onChange={(e) => {
                        const options = [...(draft.options || [])]
                        options[index] = e.target.value
                        updateField('options', options)
                      }}
                      placeholder={t('dialog.optionPlaceholder', { index: index + 1 })}
                      className="flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9 shrink-0"
                      onClick={() => updateField('options', (draft.options || []).filter((_, i) => i !== index))}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => updateField('options', [...(draft.options || []), ''])}
                >
                  <Plus className="h-3 w-3 mr-1" />
                  {t('dialog.addOption')}
                </Button>
              </div>
            </div>
          )}

          {(draft.type === 'text' || draft.type === 'paragraph') && (
            <div className="space-y-2">
              <Label className="text-sm">{t('dialog.maxLength')}</Label>
              <Input
                type="number"
                value={draft.maxLength ?? ''}
                onChange={(e) => updateField('maxLength', e.target.value ? Number(e.target.value) : null)}
                placeholder={t('dialog.unlimited')}
              />
            </div>
          )}

          {draft.type === 'number' && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-sm">{t('dialog.minValue')}</Label>
                <Input
                  type="number"
                  value={draft.min ?? ''}
                  onChange={(e) => updateField('min', e.target.value ? Number(e.target.value) : null)}
                  placeholder={t('dialog.unlimited')}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm">{t('dialog.maxValue')}</Label>
                <Input
                  type="number"
                  value={draft.max ?? ''}
                  onChange={(e) => updateField('max', e.target.value ? Number(e.target.value) : null)}
                  placeholder={t('dialog.unlimited')}
                />
              </div>
            </div>
          )}

          <div className="space-y-2">
            <Label className="text-sm">{t('dialog.defaultValue')}</Label>
            {draft.type === 'select' && (draft.options?.length ?? 0) > 0 ? (
              <Select
                value={draft.default || ''}
                onValueChange={(value) => updateField('default', value || null)}
              >
                <SelectTrigger>
                  <SelectValue>
                    {draft.default || <span className="text-muted-foreground">{t('dialog.selectDefault')}</span>}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {(draft.options || []).filter(Boolean).map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : draft.type === 'checkbox' ? (
              <div className="flex items-center gap-2 pt-1">
                <Checkbox
                  checked={draft.default === 'true'}
                  onCheckedChange={(checked) => updateField('default', checked ? 'true' : 'false')}
                />
                <span className="text-sm text-muted-foreground">{t('dialog.defaultChecked')}</span>
              </div>
            ) : (
              <Input
                type={draft.type === 'number' ? 'number' : 'text'}
                value={draft.default || ''}
                onChange={(e) => updateField('default', e.target.value || null)}
                placeholder={t('dialog.defaultValue')}
              />
            )}
          </div>

          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-2">
              <Checkbox
                checked={draft.required}
                onCheckedChange={(checked) => updateField('required', !!checked)}
              />
              <Label className="text-sm">{t('dialog.required')}</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                checked={draft.hidden || false}
                onCheckedChange={(checked) => updateField('hidden', !!checked)}
              />
              <Label className="text-sm">{t('dialog.hidden')}</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>{t('dialog.cancel')}</Button>
          <Button onClick={handleSave}>{t('dialog.save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface VariableItemProps {
  variable: VariableDefinition
  onEdit: () => void
  onDelete: () => void
}

function VariableItem({ variable, onEdit, onDelete }: VariableItemProps) {
  const [isDeleteHover, setIsDeleteHover] = React.useState(false)
  const typeConfig = variableTypes.find((t) => t.value === variable.type)
  const TypeIcon = typeConfig?.icon || Type

  return (
    <div className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-colors group ${
      isDeleteHover ? 'bg-destructive/10 border-destructive/30' : 'bg-background hover:bg-muted/30'
    }`}>
      <div className="w-6 h-6 rounded bg-muted/50 flex items-center justify-center shrink-0">
        {React.createElement(TypeIcon, { className: "h-3 w-3 text-muted-foreground" })}
      </div>
      <div className="flex items-center gap-1.5 text-primary">
        <span className="text-xs font-mono opacity-60">{'{x}'}</span>
        <span className="text-xs font-medium">{variable.name}</span>
        {variable.label && (
          <>
            <span className="text-muted-foreground text-xs">·</span>
            <span className="text-xs text-muted-foreground">{variable.label}</span>
          </>
        )}
      </div>
      <div className="ml-auto flex items-center gap-1.5">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 cursor-pointer hover:bg-primary/10 hover:text-primary"
            onClick={(e) => {
              e.stopPropagation()
              onEdit()
            }}
          >
            <Pencil className="h-3 w-3 text-muted-foreground hover:text-primary" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={`h-6 w-6 cursor-pointer hover:bg-destructive/10 hover:text-destructive`}
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            onMouseEnter={() => setIsDeleteHover(true)}
            onMouseLeave={() => setIsDeleteHover(false)}
          >
            <Trash2 className="h-3 w-3 text-muted-foreground" />
          </Button>
        </div>
        <div className="flex items-center gap-1.5 group-hover:hidden">
          {variable.required && (
            <Badge variant="outline" className="text-[10px] h-4 px-1.5 font-normal">
              REQUIRED
            </Badge>
          )}
          <span className="text-[10px] text-muted-foreground">{typeToDataType[variable.type]}</span>
          {React.createElement(TypeIcon, { className: "h-3 w-3 text-muted-foreground" })}
        </div>
      </div>
    </div>
  )
}

interface VariableEditorProps {
  variables: VariableDefinition[]
  onChange: (variables: VariableDefinition[]) => void
  editingIndex?: number | null
  onEditingIndexChange?: (index: number | null) => void
  isNewVariable?: boolean
}

export function VariableEditor({ variables, onChange, editingIndex: externalEditingIndex, onEditingIndexChange, isNewVariable }: VariableEditorProps) {
  const t = useTranslations('agents.orchestration.variables')
  const [internalEditingIndex, setInternalEditingIndex] = React.useState<number | null>(null)
  const editingIndex = externalEditingIndex !== undefined ? externalEditingIndex : internalEditingIndex
  const setEditingIndex = onEditingIndexChange || setInternalEditingIndex
  const savedRef = React.useRef(false)

  const updateVariable = (index: number, variable: VariableDefinition) => {
    const newVariables = [...variables]
    newVariables[index] = variable
    onChange(newVariables)
  }

  const deleteVariable = (index: number) => {
    onChange(variables.filter((_, i) => i !== index))
    if (editingIndex === index) {
      setEditingIndex(null)
    }
  }

  const handleSave = (variable: VariableDefinition) => {
    if (editingIndex !== null) {
      savedRef.current = true
      updateVariable(editingIndex, variable)
      setEditingIndex(null)
    }
  }

  const handleDialogClose = () => {
    // 如果是新添加的变量且没有保存过，取消时删除它
    if (isNewVariable && editingIndex !== null && !savedRef.current) {
      deleteVariable(editingIndex)
    } else {
      setEditingIndex(null)
    }
    savedRef.current = false
  }

  // 当 editingIndex 变化时重置 savedRef
  React.useEffect(() => {
    if (editingIndex !== null) {
      savedRef.current = false
    }
  }, [editingIndex])

  if (variables.length === 0) {
    return (
      <p className="text-xs text-muted-foreground py-2">
        {t('empty')}
      </p>
    )
  }

  return (
    <>
      <div className="space-y-2">
        {variables.map((variable, index) => (
          <VariableItem
            key={index}
            variable={variable}
            onEdit={() => setEditingIndex(index)}
            onDelete={() => deleteVariable(index)}
          />
        ))}
      </div>
      {editingIndex !== null && variables[editingIndex] && (
        <VariableEditDialog
          variable={variables[editingIndex]}
          open={true}
          onOpenChange={(open) => !open && handleDialogClose()}
          onSave={handleSave}
          onCancel={handleDialogClose}
        />
      )}
    </>
  )
}

export function createNewVariable(
  type: VariableType,
  existingVariables: VariableDefinition[]
): VariableDefinition {
  const baseName = 'var'
  let name = baseName
  let counter = 1
  while (existingVariables.some((v) => v.name === name)) {
    name = `${baseName}_${counter}`
    counter++
  }

  return {
    name,
    type,
    label: null,
    required: false,
    hidden: false,
    default: type === 'checkbox' ? 'false' : null,
    description: null,
    options: type === 'select' ? ['选项1', '选项2'] : null,
    maxLength: null,
  }
}
