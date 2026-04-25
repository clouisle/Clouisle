'use client'

import * as React from 'react'
import { Plus, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { TypeKind, TypeSpec } from '@/lib/workflow/type-spec'

const ALL_KINDS: TypeKind[] = [
  'string',
  'number',
  'boolean',
  'object',
  'array',
  'any',
  'null',
  'file',
  'image',
  'files',
  'images',
]

function getKindLabelKey(kind: TypeKind): string {
  if (kind === 'files') return 'dialogs.parameterEdit.kindFiles'
  if (kind === 'images') return 'dialogs.parameterEdit.kindImages'
  return `dialogs.parameterEdit.type${kind.charAt(0).toUpperCase() + kind.slice(1)}`
}

interface TypeSpecEditorProps {
  /** Current spec; undefined renders as `any`. */
  value: TypeSpec | undefined
  onChange: (next: TypeSpec) => void
  /** When true, kind is fixed (used when the editor is rendered for a code-node
   *  output whose top-level kind is selected separately). Inner item / field
   *  editors call without this flag. */
  lockKind?: boolean
  className?: string
}

export function TypeSpecEditor({
  value,
  onChange,
  lockKind,
  className,
}: TypeSpecEditorProps) {
  const t = useTranslations('workflow')
  const spec: TypeSpec = value ?? { kind: 'any' }

  const handleKindChange = (kind: TypeKind) => {
    onChange({ kind })
  }

  return (
    <div className={cn('space-y-2', className)}>
      {!lockKind && (
        <Select value={spec.kind} onValueChange={(v) => handleKindChange(v as TypeKind)}>
          <SelectTrigger size="xs">
            <SelectValue>{t(getKindLabelKey(spec.kind))}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {ALL_KINDS.map((k) => (
              <SelectItem key={k} value={k} className="text-xs">
                {t(getKindLabelKey(k))}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {spec.kind === 'array' && (
        <div className="ml-3 border-l pl-3">
          <div className="text-[10px] text-muted-foreground mb-1">
            {t('configCode.itemType')}
          </div>
          <TypeSpecEditor
            value={spec.item}
            onChange={(item) => onChange({ ...spec, item })}
          />
        </div>
      )}

      {spec.kind === 'object' && (
        <ObjectFieldsEditor
          fields={spec.fields ?? {}}
          onChange={(fields) =>
            onChange({
              ...spec,
              fields: Object.keys(fields).length ? fields : undefined,
            })
          }
        />
      )}
    </div>
  )
}

interface ObjectFieldsEditorProps {
  fields: Record<string, TypeSpec>
  onChange: (next: Record<string, TypeSpec>) => void
}

function ObjectFieldsEditor({ fields, onChange }: ObjectFieldsEditorProps) {
  const t = useTranslations('workflow')
  const [open, setOpen] = React.useState(true)
  const entries = React.useMemo(() => Object.entries(fields), [fields])

  const handleAdd = () => {
    let candidate = 'field'
    let n = 1
    while (candidate in fields) {
      n += 1
      candidate = `field${n}`
    }
    onChange({ ...fields, [candidate]: { kind: 'string' } })
  }

  const handleRename = (oldKey: string, newKey: string) => {
    if (!newKey || newKey === oldKey) return
    if (newKey in fields) return
    const next: Record<string, TypeSpec> = {}
    for (const [k, v] of entries) {
      next[k === oldKey ? newKey : k] = v
    }
    onChange(next)
  }

  const handleUpdate = (key: string, type: TypeSpec) => {
    onChange({ ...fields, [key]: type })
  }

  const handleRemove = (key: string) => {
    const rest: Record<string, TypeSpec> = {}
    for (const [k, v] of entries) {
      if (k !== key) rest[k] = v
    }
    onChange(rest)
  }

  return (
    <div className="ml-3 border-l pl-3 space-y-1.5">
      <div className="flex items-center justify-between">
        <button
          type="button"
          className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
          onClick={() => setOpen((o) => !o)}
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {t('configCode.objectFields')} ({entries.length})
        </button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-5 w-5"
          onClick={handleAdd}
        >
          <Plus className="h-3 w-3" />
        </Button>
      </div>
      {open && (
        <div className="space-y-1.5">
          {entries.length === 0 && (
            <div className="text-[10px] text-muted-foreground italic">
              {t('configCode.noFields')}
            </div>
          )}
          {entries.map(([key, type]) => (
            <div key={key} className="rounded-md bg-muted/40 p-1.5 space-y-1">
              <div className="flex items-center gap-1">
                <Input
                  value={key}
                  onBlur={(e) => handleRename(key, e.target.value.trim())}
                  onChange={() => {}}
                  defaultValue={key}
                  className="h-6 text-xs font-mono flex-1"
                  placeholder="field"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 text-destructive hover:text-destructive"
                  onClick={() => handleRemove(key)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
              <TypeSpecEditor value={type} onChange={(t) => handleUpdate(key, t)} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
