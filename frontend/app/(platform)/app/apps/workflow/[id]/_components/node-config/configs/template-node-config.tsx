'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, ChevronDown, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import { CodeEditor } from '../components/code-editor'
import { TemplateInputDialog } from '../dialogs/template-input-dialog'
import type { AvailableVariable } from '../types'
import { extractVariableDisplayName } from '../types'
import { 
  TemplateConfig, 
  TemplateInput,
  defaultTemplateConfig,
} from '../../nodes/template-node'

interface TemplateNodeConfigProps {
  config: TemplateConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: TemplateConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function TemplateNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: TemplateNodeConfigProps) {
  const t = useTranslations('workflow')
  const [outputOpen, setOutputOpen] = React.useState(true)
  const [inputDialogOpen, setInputDialogOpen] = React.useState(false)
  const [editingInput, setEditingInput] = React.useState<TemplateInput | null>(null)

  // 确保 config 有默认值
  const safeConfig: TemplateConfig = {
    ...defaultTemplateConfig,
    ...config,
    inputs: config.inputs || [],
  }

  // 打开添加弹窗
  const handleOpenAddDialog = () => {
    setEditingInput(null)
    setInputDialogOpen(true)
  }

  // 打开编辑弹窗
  const handleOpenEditDialog = (input: TemplateInput) => {
    setEditingInput(input)
    setInputDialogOpen(true)
  }

  // 保存输入变量（添加或更新）
  const handleSaveInput = (input: TemplateInput) => {
    const existingIndex = safeConfig.inputs.findIndex(i => i.id === input.id)
    if (existingIndex >= 0) {
      // 更新
      onConfigChange({
        ...safeConfig,
        inputs: safeConfig.inputs.map(i => i.id === input.id ? input : i),
      })
    } else {
      // 添加
      onConfigChange({
        ...safeConfig,
        inputs: [...safeConfig.inputs, input],
      })
    }
  }

  // 删除输入变量
  const handleDeleteInput = (id: string) => {
    onConfigChange({
      ...safeConfig,
      inputs: safeConfig.inputs.filter(i => i.id !== id),
    })
  }

  return (
    <div className="space-y-4">
      {/* 输入变量 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">{t('configTemplate.inputVariables')}</Label>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleOpenAddDialog}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        
        {safeConfig.inputs.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2 text-center bg-muted/30 rounded-md">
            {t('configTemplate.noInputVariables')}
          </p>
        ) : (
          <div className="space-y-1.5">
            {safeConfig.inputs.map((input) => {
              const hasNameError = input.name && !isValidVariableName(input.name)
              const isDuplicate = safeConfig.inputs.filter(i => i.name === input.name).length > 1
              
              return (
                <div
                  key={input.id}
                  className="group flex items-center justify-between bg-muted/30 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className={cn(
                      'text-xs font-mono font-medium',
                      (hasNameError || isDuplicate) && 'text-destructive'
                    )}>
                      {input.name}
                    </span>
                    {input.value && (
                      <span className="text-xs text-muted-foreground truncate">
                        = {input.valueSource && `${input.valueSource} / `}{extractVariableDisplayName(input.value)}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-foreground"
                      onClick={() => handleOpenEditDialog(input)}
                    >
                      <Pencil className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-destructive"
                      onClick={() => handleDeleteInput(input.id)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        
        {/* 错误提示 */}
        {safeConfig.inputs.some(i => i.name && !isValidVariableName(i.name)) && (
          <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableNameFormat')}</p>
        )}
        {(() => {
          const names = safeConfig.inputs.map(i => i.name).filter(Boolean)
          const hasDuplicates = new Set(names).size !== names.length
          return hasDuplicates && (
            <p className="text-[10px] text-destructive">{t('configCommon.duplicateVariableName')}</p>
          )
        })()}
      </div>

      {/* 输入变量弹窗 */}
      <TemplateInputDialog
        open={inputDialogOpen}
        onOpenChange={setInputDialogOpen}
        editingInput={editingInput}
        existingInputs={safeConfig.inputs}
        variables={variables}
        variableSearch={variableSearch}
        openVariablePopover={openVariablePopover}
        onVariableSearchChange={onVariableSearchChange}
        onOpenVariablePopoverChange={onOpenVariablePopoverChange}
        onSave={handleSaveInput}
      />
      
      {/* 代码/模板编辑器 */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">{t('configCommon.code')}</Label>
        <CodeEditor
          value={safeConfig.template}
          language="jinja2"
          onChange={(template) => onConfigChange({ ...safeConfig, template })}
          minHeight={160}
          showLanguageSelector={false}
        />
      </div>
      
      {/* 输出变量 - 可折叠 */}
      <Collapsible open={outputOpen} onOpenChange={setOutputOpen}>
        <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
          <ChevronDown className={cn(
            "h-3.5 w-3.5 transition-transform",
            !outputOpen && "-rotate-90"
          )} />
          <span>{t('configCommon.outputVariables')}</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2">
          <div className="bg-muted/30 rounded-lg p-3 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-medium">{safeConfig.outputVariable}</span>
              <span className="text-xs text-muted-foreground">string</span>
            </div>
            <p className="text-[10px] text-muted-foreground">{safeConfig.outputDescription}</p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
