'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { MessageSquare } from 'lucide-react'
import { type VariableDefinition, type VariableType } from '@/lib/api'
import { PromptVariableEditor, type PromptVariableItem } from '@/components/prompt-variable-editor'

interface PromptEditorProps {
  value: string
  onChange: (value: string) => void
  variables: VariableDefinition[]
  onAddVariable: (name: string, type: VariableType) => void
  placeholder?: string
  className?: string
  enableFileUpload?: boolean
}

interface SystemVariable {
  name: string
  label: string
  description: string
  icon: React.ElementType
}

export function PromptEditor({
  value,
  onChange,
  variables,
  onAddVariable,
  placeholder,
  className,
}: PromptEditorProps) {
  const t = useTranslations('agents.orchestration.prompt')

  const systemVariables = React.useMemo<SystemVariable[]>(() => {
    const vars: SystemVariable[] = [
      {
        name: 'query',
        label: t('systemVars.query'),
        description: t('systemVars.queryDesc'),
        icon: MessageSquare,
      },
    ]

    return vars
  }, [t])

  const promptVariables = React.useMemo<PromptVariableItem[]>(() => {
    const mappedSystemVariables = systemVariables.map((variable) => ({
      ref: variable.name,
      name: variable.name,
      label: variable.label,
      isSystem: true,
      icon: variable.icon,
    }))

    const mappedVariables = variables.map((variable) => ({
      ref: variable.name,
      name: variable.name,
      label: variable.label ?? undefined,
      isSystem: false,
    }))

    return [...mappedSystemVariables, ...mappedVariables]
  }, [systemVariables, variables])

  const handleCreateVariable = React.useCallback((name: string) => {
    onAddVariable(name, 'text')
    onChange(value.replace(/\{\{[^{}\s]*$/, `{{${name}}}`))
  }, [onAddVariable, onChange, value])

  return (
    <PromptVariableEditor
      value={value}
      onChange={onChange}
      variables={promptVariables}
      placeholder={placeholder}
      className={className}
      editorClassName="min-h-50 max-h-[50vh] w-full resize-none border-0 bg-transparent p-0 text-sm leading-relaxed focus:outline-none focus-visible:ring-0 shadow-none overflow-y-auto"
      groupMode="system-user"
      systemGroupLabel={t('systemVariables')}
      userGroupLabel={t('userVariables')}
      allowCreateVariable
      onCreateVariable={handleCreateVariable}
      showUndefinedWarnings
      onUndefinedVariableClick={(name) => onAddVariable(name, 'text')}
      noVariablesText={t('noVariables')}
      variableNotFoundText={(query) => t('variableNotFound', { query })}
      createVariableText={(name) => t('createVariable', { name })}
      undefinedVariablesHintText={t('undefinedVariablesHint')}
    />
  )
}
