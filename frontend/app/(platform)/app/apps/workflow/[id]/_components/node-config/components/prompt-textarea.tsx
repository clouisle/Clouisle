'use client'

import * as React from 'react'
import { PromptVariableEditor, type PromptVariableItem } from '@/components/prompt-variable-editor'
import type { AvailableVariable } from '../types'

interface PromptTextareaProps {
  value: string
  onChange: (value: string) => void
  variables: AvailableVariable[]
  placeholder?: string
  className?: string
  minHeight?: string
}

export function PromptTextarea({
  value,
  onChange,
  variables,
  placeholder,
  className,
  minHeight = 'min-h-20',
}: PromptTextareaProps) {
  const promptVariables = React.useMemo<PromptVariableItem[]>(() => {
    return variables.map((variable) => ({
      ref: variable.id,
      name: variable.name,
      label: variable.groupLabel,
      groupId: variable.group,
      groupLabel: variable.groupLabel,
      isSystem: variable.isSystem,
      type: variable.type,
    }))
  }, [variables])

  return (
    <PromptVariableEditor
      value={value}
      onChange={onChange}
      variables={promptVariables}
      placeholder={placeholder}
      groupMode="custom"
      className={className}
      minHeightClassName={minHeight}
      editorClassName="w-full text-xs p-3 rounded-md border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 overflow-auto whitespace-pre-wrap"
    />
  )
}
