'use client'

import * as React from 'react'
import { Plus, Trash2, ChevronDown, Pencil, File, Image, Files, Images } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import { FileToUrlInputDialog } from '../dialogs'
import type { AvailableVariable } from '../types'
import { 
  FileToUrlConfig, 
  FileToUrlInput,
  defaultFileToUrlConfig,
} from '../../nodes/file-to-url-node'

// 类型图标映射
const typeIcons: Record<string, React.ElementType> = {
  file: File,
  image: Image,
  files: Files,
  images: Images,
}

// 类型标签映射
const typeLabels: Record<string, string> = {
  file: '文件',
  image: '图片',
  files: '多文件',
  images: '多图片',
}

interface FileToUrlNodeConfigProps {
  config: FileToUrlConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: FileToUrlConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function FileToUrlNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: FileToUrlNodeConfigProps) {
  const [outputOpen, setOutputOpen] = React.useState(true)
  const [inputDialogOpen, setInputDialogOpen] = React.useState(false)
  const [editingInput, setEditingInput] = React.useState<FileToUrlInput | null>(null)

  // 确保 config 有默认值
  const safeConfig: FileToUrlConfig = {
    ...defaultFileToUrlConfig,
    ...config,
    inputs: config.inputs || [],
  }

  // 过滤出文件类型的变量
  const fileVariables = variables.filter(v => v.isFile)

  // 打开添加弹窗
  const handleOpenAddDialog = () => {
    setEditingInput(null)
    setInputDialogOpen(true)
  }

  // 打开编辑弹窗
  const handleOpenEditDialog = (input: FileToUrlInput) => {
    setEditingInput(input)
    setInputDialogOpen(true)
  }

  // 保存输入（添加或更新）
  const handleSaveInput = (input: FileToUrlInput) => {
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

  // 删除输入
  const handleDeleteInput = (id: string) => {
    onConfigChange({
      ...safeConfig,
      inputs: safeConfig.inputs.filter(i => i.id !== id),
    })
  }

  return (
    <div className="space-y-4">
      {/* 输入配置 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">文件输入</Label>
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
          <div className="text-center py-4 bg-muted/30 rounded-md">
            <p className="text-xs text-muted-foreground">
              暂无输入，点击 + 添加文件变量
            </p>
            {fileVariables.length === 0 && (
              <p className="text-[10px] text-muted-foreground mt-1">
                提示：请先在开始节点添加文件/图片类型的参数
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-1.5">
            {safeConfig.inputs.map((input) => {
              const hasNameError = input.name && !isValidVariableName(input.name)
              const isDuplicate = safeConfig.inputs.filter(i => i.name === input.name).length > 1
              const TypeIcon = typeIcons[input.sourceType] || File
              
              return (
                <div
                  key={input.id}
                  className="group flex items-center justify-between bg-muted/30 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <TypeIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className={cn(
                      'text-xs font-mono font-medium',
                      (hasNameError || isDuplicate) && 'text-destructive'
                    )}>
                      {input.name}
                    </span>
                    {input.sourceVariable && (
                      <span className="text-xs text-muted-foreground truncate">
                        ← {input.sourceVariable.replace(/\{\{|\}\}/g, '')}
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
          <p className="text-[10px] text-destructive">变量名格式无效（只能包含字母、数字、下划线，不能以数字开头）</p>
        )}
        {(() => {
          const names = safeConfig.inputs.map(i => i.name).filter(Boolean)
          const hasDuplicates = new Set(names).size !== names.length
          return hasDuplicates && (
            <p className="text-[10px] text-destructive">存在重复的变量名</p>
          )
        })()}
      </div>

      {/* 输入弹窗 */}
      <FileToUrlInputDialog
        open={inputDialogOpen}
        onOpenChange={setInputDialogOpen}
        editingInput={editingInput}
        existingInputs={safeConfig.inputs}
        variables={fileVariables}
        variableSearch={variableSearch}
        openVariablePopover={openVariablePopover}
        onVariableSearchChange={onVariableSearchChange}
        onOpenVariablePopoverChange={onOpenVariablePopoverChange}
        onSave={handleSaveInput}
      />

      {/* URL 选项 */}
      <div className="space-y-3">
        <Label className="text-xs font-medium">选项</Label>
        <div className="flex items-center justify-between bg-muted/30 rounded-lg px-3 py-2">
          <div className="space-y-0.5">
            <span className="text-xs">生成绝对 URL</span>
            <p className="text-[10px] text-muted-foreground">包含完整的域名前缀</p>
          </div>
          <Switch
            checked={safeConfig.ensureAbsolute}
            onCheckedChange={(checked) => onConfigChange({
              ...safeConfig,
              ensureAbsolute: checked,
            })}
          />
        </div>
      </div>
      
      {/* 输出变量 - 可折叠 */}
      <Collapsible open={outputOpen} onOpenChange={setOutputOpen}>
        <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
          <ChevronDown className={cn(
            "h-3.5 w-3.5 transition-transform",
            !outputOpen && "-rotate-90"
          )} />
          <span>输出变量</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2">
          <div className="space-y-1.5">
            {safeConfig.inputs.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-2 bg-muted/30 rounded-lg">
                添加输入后将自动生成对应的输出变量
              </p>
            ) : (
              safeConfig.inputs.map((input) => {
                const isMultiple = input.sourceType === 'files' || input.sourceType === 'images'
                return (
                  <div key={input.id} className="bg-muted/30 rounded-lg p-3 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-medium">{input.name}</span>
                      <span className="text-xs text-muted-foreground">
                        {isMultiple ? 'string[]' : 'string'}
                      </span>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      {isMultiple ? 'URL 数组' : '文件 URL'}
                    </p>
                  </div>
                )
              })
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
