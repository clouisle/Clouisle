'use client'

import * as React from 'react'
import { Variable, Plus, AlertCircle, FileText, MessageSquare } from 'lucide-react'
import { type VariableDefinition, type VariableType } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface PromptEditorProps {
  value: string
  onChange: (value: string) => void
  variables: VariableDefinition[]
  onAddVariable: (name: string, type: VariableType) => void
  placeholder?: string
  className?: string
  enableFileUpload?: boolean
}

// System variables that are auto-injected based on features
interface SystemVariable {
  name: string
  label: string
  description: string
  icon: React.ElementType
}

// 解析提示词中的所有变量引用
function parseVariableReferences(text: string): string[] {
  const regex = /\{\{(\w+)\}\}/g
  const matches: string[] = []
  let match
  while ((match = regex.exec(text)) !== null) {
    if (!matches.includes(match[1])) {
      matches.push(match[1])
    }
  }
  return matches
}

// 检查是否在 {{ 和 }} 之间
function getVariableContext(text: string, cursorPos: number): { isInVariable: boolean; query: string; startPos: number } {
  const textBeforeCursor = text.substring(0, cursorPos)
  const lastOpenBrace = textBeforeCursor.lastIndexOf('{{')
  const lastCloseBrace = textBeforeCursor.lastIndexOf('}}')

  if (lastOpenBrace > lastCloseBrace && lastOpenBrace !== -1) {
    const query = textBeforeCursor.substring(lastOpenBrace + 2)
    if (!/\s/.test(query)) {
      return { isInVariable: true, query, startPos: lastOpenBrace }
    }
  }
  return { isInVariable: false, query: '', startPos: -1 }
}

// 高亮渲染文本中的变量
function renderHighlightedText(text: string, definedVarNames: string[]): React.ReactNode[] {
  const parts: React.ReactNode[] = []
  const regex = /(\{\{\w+\}\})/g
  let lastIndex = 0
  let match

  while ((match = regex.exec(text)) !== null) {
    // 添加变量之前的普通文本
    if (match.index > lastIndex) {
      parts.push(
        <span key={`text-${lastIndex}`}>
          {text.substring(lastIndex, match.index)}
        </span>
      )
    }

    // 添加变量（带高亮）
    const varMatch = match[1]
    const varName = varMatch.slice(2, -2) // 移除 {{ 和 }}
    const isDefined = definedVarNames.includes(varName)

    parts.push(
      <span
        key={`var-${match.index}`}
        className={cn(
          'font-medium',
          isDefined 
            ? 'text-blue-600 dark:text-blue-400' 
            : 'text-amber-600 dark:text-amber-400'
        )}
      >
        {varMatch}
      </span>
    )

    lastIndex = match.index + match[0].length
  }

  // 添加剩余的普通文本
  if (lastIndex < text.length) {
    parts.push(
      <span key={`text-${lastIndex}`}>
        {text.substring(lastIndex)}
      </span>
    )
  }

  // 如果文本为空，返回空数组
  if (parts.length === 0 && text.length === 0) {
    return []
  }

  return parts
}

export function PromptEditor({
  value,
  onChange,
  variables,
  onAddVariable,
  placeholder,
  className,
  enableFileUpload,
}: PromptEditorProps) {
  'use no memo'  // Disable React Compiler optimization for this component
  const containerRef = React.useRef<HTMLDivElement>(null)
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)
  const highlightRef = React.useRef<HTMLDivElement>(null)
  const popoverRef = React.useRef<HTMLDivElement>(null)
  const [showSuggestions, setShowSuggestions] = React.useState(false)
  const [suggestionPosition, setSuggestionPosition] = React.useState({ top: 0, left: 0 })
  const [searchQuery, setSearchQuery] = React.useState('')
  const [selectedIndex, setSelectedIndex] = React.useState(0)
  const variableStartPosRef = React.useRef(-1)

  // System variables based on enabled features
  const systemVariables = React.useMemo<SystemVariable[]>(() => {
    const vars: SystemVariable[] = [
      // query is always available - represents user input
      {
        name: 'query',
        label: '用户输入',
        description: '用户当前的提问内容',
        icon: MessageSquare,
      },
    ]
    if (enableFileUpload) {
      vars.push({
        name: 'fileContent',
        label: '文件内容',
        description: '上传文件的解析内容',
        icon: FileText,
      })
    }
    return vars
  }, [enableFileUpload])

  // 获取未定义的变量
  const referencedVars = parseVariableReferences(value)
  // Stabilize definedVarNames with useMemo to prevent React Compiler issues
  const definedVarNames = React.useMemo(() => variables.map(v => v.name), [variables])
  const systemVarNames = React.useMemo(() => systemVariables.map(v => v.name), [systemVariables])
  // 未定义变量排除系统变量
  const undefinedVars = referencedVars.filter(name => !definedVarNames.includes(name) && !systemVarNames.includes(name))

  // 过滤变量建议 (用户定义的变量)
  const filteredVariables = React.useMemo(() => 
    variables.filter(v => v.name.toLowerCase().includes(searchQuery.toLowerCase())),
    [variables, searchQuery]
  )

  // 过滤系统变量建议
  const filteredSystemVariables = React.useMemo(() => 
    systemVariables.filter(v => v.name.toLowerCase().includes(searchQuery.toLowerCase())),
    [systemVariables, searchQuery]
  )

  // 总建议数
  const totalSuggestions = filteredVariables.length + filteredSystemVariables.length

  // 同步滚动
  const handleScroll = React.useCallback(() => {
    if (textareaRef.current && highlightRef.current) {
      highlightRef.current.scrollTop = textareaRef.current.scrollTop
      highlightRef.current.scrollLeft = textareaRef.current.scrollLeft
    }
  }, [])

  // 计算建议框位置
  const updatePosition = React.useCallback((cursorPos: number) => {
    const textarea = textareaRef.current
    if (!textarea) return

    const text = textarea.value
    const textBeforeCursor = text.substring(0, cursorPos)
    
    // 简单计算：基于行数和字符位置
    const lines = textBeforeCursor.split('\n')
    const currentLineIndex = lines.length - 1
    const lineHeight = 20 // 大约的行高
    
    setSuggestionPosition({
      top: (currentLineIndex + 1) * lineHeight + 4,
      left: 0,
    })
  }, [])

  // 处理输入变化
  const handleInput = React.useCallback((e: React.FormEvent<HTMLTextAreaElement>) => {
    const textarea = e.currentTarget
    const newValue = textarea.value
    const cursorPos = textarea.selectionStart

    onChange(newValue)

    // 检查变量上下文
    const context = getVariableContext(newValue, cursorPos)
    
    if (context.isInVariable) {
      variableStartPosRef.current = context.startPos
      setSearchQuery(context.query)
      setSelectedIndex(0)
      setShowSuggestions(true)
      updatePosition(cursorPos)
    } else {
      setShowSuggestions(false)
      setSearchQuery('')
      variableStartPosRef.current = -1
    }
  }, [onChange, updatePosition])

  // 插入变量
  const insertVariable = React.useCallback((varName: string) => {
    const textarea = textareaRef.current
    if (!textarea || variableStartPosRef.current === -1) return

    const startPos = variableStartPosRef.current
    const textBefore = value.substring(0, startPos)
    const cursorPos = textarea.selectionStart
    const textAfter = value.substring(cursorPos)

    const newValue = textBefore + `{{${varName}}}` + textAfter
    onChange(newValue)
    
    setShowSuggestions(false)
    setSearchQuery('')
    variableStartPosRef.current = -1

    // 设置光标位置到变量后面
    const newCursorPos = startPos + varName.length + 4
    requestAnimationFrame(() => {
      textarea.focus()
      textarea.setSelectionRange(newCursorPos, newCursorPos)
    })
  }, [value, onChange])

  // 处理键盘事件
  const handleKeyDown = React.useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!showSuggestions) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(prev => 
          totalSuggestions > 0 ? (prev + 1) % totalSuggestions : 0
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(prev => 
          totalSuggestions > 0 
            ? (prev - 1 + totalSuggestions) % totalSuggestions 
            : 0
        )
        break
      case 'Enter':
      case 'Tab':
        if (totalSuggestions > 0) {
          e.preventDefault()
          // Determine which variable to insert based on index
          if (selectedIndex < filteredSystemVariables.length) {
            insertVariable(filteredSystemVariables[selectedIndex].name)
          } else {
            insertVariable(filteredVariables[selectedIndex - filteredSystemVariables.length].name)
          }
        }
        break
      case 'Escape':
        e.preventDefault()
        setShowSuggestions(false)
        break
    }
  }, [showSuggestions, totalSuggestions, filteredVariables, filteredSystemVariables, selectedIndex, insertVariable])

  // 处理失焦
  const handleBlur = React.useCallback((e: React.FocusEvent) => {
    // 如果焦点移到弹窗内，不关闭
    const relatedTarget = e.relatedTarget as Node | null
    if (popoverRef.current?.contains(relatedTarget)) {
      return
    }
    // 延迟关闭，让点击事件有时间处理
    setTimeout(() => {
      setShowSuggestions(false)
    }, 150)
  }, [])

  // 渲染高亮文本
  const highlightedContent = React.useMemo(() => {
    const allDefinedNames = [...definedVarNames, ...systemVarNames]
    const rendered = renderHighlightedText(value, allDefinedNames)
    // 添加一个额外的空格确保高度一致
    return [...rendered, <span key="trailing">{'\n '}</span>]
  }, [value, definedVarNames, systemVarNames])

  return (
    <div ref={containerRef} className="relative">
      {/* 高亮层 */}
      <div
        ref={highlightRef}
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words text-sm leading-relaxed',
          className
        )}
      >
        {value ? highlightedContent : (
          <span className="text-muted-foreground">{placeholder}</span>
        )}
      </div>

      {/* 输入层 */}
      <textarea
        ref={textareaRef}
        value={value}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        onScroll={handleScroll}
        placeholder=""
        className={cn(
          'min-h-50 w-full resize-none border-0 bg-transparent p-0 focus-visible:ring-0 shadow-none text-sm leading-relaxed focus:outline-none',
          'text-transparent caret-foreground selection:bg-primary/20',
          className
        )}
      />

      {/* 变量建议弹窗 */}
      {showSuggestions && (
        <div
          ref={popoverRef}
          className="absolute z-50 w-64 rounded-lg border bg-popover shadow-lg"
          style={{ top: suggestionPosition.top, left: suggestionPosition.left }}
          onMouseDown={(e) => e.preventDefault()}
        >
          <div className="p-1 max-h-48 overflow-y-auto">
            {totalSuggestions > 0 ? (
              <>
                {/* System Variables */}
                {filteredSystemVariables.length > 0 && (
                  <>
                    <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                      系统变量
                    </div>
                    {filteredSystemVariables.map((variable, index) => {
                      const Icon = variable.icon
                      return (
                        <button
                          key={variable.name}
                          type="button"
                          className={cn(
                            'w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-sm transition-colors',
                            selectedIndex === index ? 'bg-accent' : 'hover:bg-muted'
                          )}
                          onMouseDown={(e) => {
                            e.preventDefault()
                            insertVariable(variable.name)
                          }}
                        >
                          <Icon className="h-3.5 w-3.5 text-cyan-500 shrink-0" />
                          <span className="font-mono text-xs">{variable.name}</span>
                          <span className="text-xs text-muted-foreground truncate">
                            {variable.label}
                          </span>
                        </button>
                      )
                    })}
                  </>
                )}
                {/* User Variables */}
                {filteredVariables.length > 0 && (
                  <>
                    {filteredSystemVariables.length > 0 && (
                      <div className="px-2 py-1 text-xs text-muted-foreground font-medium mt-1">
                        用户变量
                      </div>
                    )}
                    {filteredVariables.map((variable, index) => (
                      <button
                        key={variable.name}
                        type="button"
                        className={cn(
                          'w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-sm transition-colors',
                          selectedIndex === index + filteredSystemVariables.length ? 'bg-accent' : 'hover:bg-muted'
                        )}
                        onMouseDown={(e) => {
                          e.preventDefault()
                          insertVariable(variable.name)
                        }}
                      >
                        <Variable className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                        <span className="font-mono text-xs">{variable.name}</span>
                        {variable.label && (
                          <span className="text-xs text-muted-foreground truncate">
                            {variable.label}
                          </span>
                        )}
                      </button>
                    ))}
                  </>
                )}
              </>
            ) : (
              <div className="px-2 py-3 text-center">
                <p className="text-xs text-muted-foreground mb-2">
                  {searchQuery ? `未找到变量 "${searchQuery}"` : '暂无变量'}
                </p>
                {searchQuery && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onMouseDown={(e) => {
                      e.preventDefault()
                      onAddVariable(searchQuery, 'text')
                      insertVariable(searchQuery)
                    }}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    创建变量 &quot;{searchQuery}&quot;
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 未定义变量警告 */}
      {undefinedVars.length > 0 && (
        <div className="mt-3 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-amber-700 dark:text-amber-400 mb-2">
                以下变量未定义，点击添加到变量列表：
              </p>
              <div className="flex flex-wrap gap-1.5">
                {undefinedVars.map(name => (
                  <Button
                    key={name}
                    variant="outline"
                    size="sm"
                    className="h-6 text-xs px-2 bg-background hover:bg-amber-500/10 border-amber-500/30"
                    onClick={() => onAddVariable(name, 'text')}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    {`{{${name}}}`}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
