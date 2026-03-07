'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Variable, Plus, AlertCircle, FileText, MessageSquare } from 'lucide-react'
import { type VariableDefinition, type VariableType } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'

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

// 变量信息类型
interface VariableInfo {
  name: string
  label?: string
  isSystem: boolean
  icon?: React.ElementType
}

function appendTextWithBreaks(parent: Node, text: string): void {
  const lines = text.split('\n')
  lines.forEach((line, index) => {
    if (index > 0) {
      parent.appendChild(document.createElement('br'))
    }
    if (line) {
      parent.appendChild(document.createTextNode(line))
    }
  })
}

function createVariableTag(variable: VariableInfo | undefined, varName: string): HTMLSpanElement {
  const tag = document.createElement('span')
  const tagClass = variable
    ? 'bg-primary/15 text-primary border-primary/20'
    : 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20'
  const displayLabel = variable?.label ?? ''

  tag.className = `variable-tag inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded text-[11px] font-medium border align-middle ${tagClass}`
  tag.contentEditable = 'false'
  tag.dataset.variable = varName

  const marker = document.createElement('span')
  marker.className = 'opacity-60 text-[10px]'
  marker.textContent = '{x}'
  tag.appendChild(marker)

  const name = document.createElement('span')
  name.textContent = varName
  tag.appendChild(name)

  if (displayLabel) {
    const label = document.createElement('span')
    label.className = 'opacity-70 text-[10px]'
    label.textContent = displayLabel
    tag.appendChild(label)
  }

  return tag
}

function renderEditorContent(editor: HTMLElement, text: string, variableMap: Map<string, VariableInfo>): void {
  if (!text) {
    editor.replaceChildren()
    return
  }

  const fragment = document.createDocumentFragment()
  const regex = /(\{\{\w+\}\})/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      appendTextWithBreaks(fragment, text.substring(lastIndex, match.index))
    }

    const varName = match[1].slice(2, -2)
    const variable = variableMap.get(varName)
    fragment.appendChild(createVariableTag(variable, varName))

    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    appendTextWithBreaks(fragment, text.substring(lastIndex))
  }

  editor.replaceChildren(fragment)
}

// 将 HTML 转换回纯文本
function htmlToText(element: HTMLElement): string {
  let result = ''

  element.childNodes.forEach((node, index) => {
    if (node.nodeType === Node.TEXT_NODE) {
      result += node.textContent || ''
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node as HTMLElement
      const varName = el.getAttribute('data-variable')
      if (varName) {
        result += `{{${varName}}}`
      } else if (el.tagName === 'BR') {
        result += '\n'
      } else if (el.tagName === 'DIV' || el.tagName === 'P') {
        // 浏览器在 contentEditable 中按 Enter 会产生 <div> 或 <p>
        // 需要在块级元素前添加换行（跳过第一个子节点）
        if (index > 0) {
          result += '\n'
        }
        result += htmlToText(el)
      } else {
        result += htmlToText(el)
      }
    }
  })

  return result
}

// 获取光标在纯文本中的位置
function getCursorPosition(containerEl: HTMLElement): number {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return 0
  
  const range = selection.getRangeAt(0)
  let pos = 0
  let found = false
  
  const traverse = (node: Node): boolean => {
    if (found) return true
    
    if (node === range.startContainer) {
      if (node.nodeType === Node.TEXT_NODE) {
        pos += range.startOffset
      }
      found = true
      return true
    }
    
    if (node.nodeType === Node.TEXT_NODE) {
      pos += (node.textContent || '').length
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node as HTMLElement
      const varName = el.getAttribute?.('data-variable')
      if (varName) {
        if (range.startContainer === el || el.contains(range.startContainer)) {
          found = true
          return true
        }
        pos += varName.length + 4 // {{varName}}
        return false
      }
      if (el.tagName === 'BR') {
        pos += 1
        return false
      }
      for (const child of Array.from(node.childNodes)) {
        if (traverse(child)) return true
      }
    }
    return false
  }
  
  traverse(containerEl)
  return pos
}

// 设置光标位置
function setCursorPosition(containerEl: HTMLElement, targetPos: number): void {
  let currentPos = 0
  
  const traverse = (node: Node): { node: Node; offset: number } | null => {
    if (node.nodeType === Node.TEXT_NODE) {
      const textLen = (node.textContent || '').length
      if (currentPos + textLen >= targetPos) {
        return { node, offset: targetPos - currentPos }
      }
      currentPos += textLen
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node as HTMLElement
      const varName = el.getAttribute?.('data-variable')
      if (varName) {
        const varLen = varName.length + 4
        if (currentPos + varLen >= targetPos) {
          const parent = el.parentNode
          if (parent) {
            const idx = Array.from(parent.childNodes).indexOf(el as ChildNode)
            return { node: parent, offset: idx + 1 }
          }
        }
        currentPos += varLen
        return null
      }
      if (el.tagName === 'BR') {
        if (currentPos + 1 >= targetPos) {
          const parent = el.parentNode
          if (parent) {
            const idx = Array.from(parent.childNodes).indexOf(el as ChildNode)
            return { node: parent, offset: idx + 1 }
          }
        }
        currentPos += 1
        return null
      }
      for (const child of Array.from(node.childNodes)) {
        const result = traverse(child)
        if (result) return result
      }
    }
    return null
  }
  
  const result = traverse(containerEl)
  if (result) {
    const selection = window.getSelection()
    if (selection) {
      const range = document.createRange()
      range.setStart(result.node, result.offset)
      range.collapse(true)
      selection.removeAllRanges()
      selection.addRange(range)
    }
  }
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
  const t = useTranslations('agents.orchestration.prompt')
  const containerRef = React.useRef<HTMLDivElement>(null)
  const editorRef = React.useRef<HTMLDivElement>(null)
  const popoverRef = React.useRef<HTMLDivElement>(null)
  const [showSuggestions, setShowSuggestions] = React.useState(false)
  const [suggestionPosition, setSuggestionPosition] = React.useState({ top: 0, left: 0 })
  const [searchQuery, setSearchQuery] = React.useState('')
  const [selectedIndex, setSelectedIndex] = React.useState(0)
  const variableStartPosRef = React.useRef(-1)
  const isComposingRef = React.useRef(false)
  const lastValueRef = React.useRef('')  // 初始化为空字符串，而不是 value
  const isInternalUpdateRef = React.useRef(false)
  const isMountedRef = React.useRef(false)

  // System variables based on enabled features
  const systemVariables = React.useMemo<SystemVariable[]>(() => {
    const vars: SystemVariable[] = [
      {
        name: 'query',
        label: t('systemVars.query'),
        description: t('systemVars.queryDesc'),
        icon: MessageSquare,
      },
    ]
    if (enableFileUpload) {
      vars.push({
        name: 'fileContent',
        label: t('systemVars.fileContent'),
        description: t('systemVars.fileContentDesc'),
        icon: FileText,
      })
    }
    return vars
  }, [enableFileUpload, t])

  // 构建变量名到变量信息的映射
  const variableMap = React.useMemo(() => {
    const map = new Map<string, VariableInfo>()
    // 系统变量
    systemVariables.forEach(v => map.set(v.name, { 
      name: v.name, 
      label: v.label, 
      isSystem: true,
      icon: v.icon 
    }))
    // 用户变量
    variables.forEach(v => map.set(v.name, {
      name: v.name,
      label: v.label ?? undefined,
      isSystem: false
    }))
    return map
  }, [variables, systemVariables])

  // 获取未定义的变量
  const referencedVars = parseVariableReferences(value)
  const definedVarNames = React.useMemo(() => variables.map(v => v.name), [variables])
  const systemVarNames = React.useMemo(() => systemVariables.map(v => v.name), [systemVariables])
  const undefinedVars = referencedVars.filter(name => !definedVarNames.includes(name) && !systemVarNames.includes(name))

  // 过滤变量建议
  const filteredVariables = React.useMemo(() => 
    variables.filter(v => v.name.toLowerCase().includes(searchQuery.toLowerCase())),
    [variables, searchQuery]
  )

  const filteredSystemVariables = React.useMemo(() => 
    systemVariables.filter(v => v.name.toLowerCase().includes(searchQuery.toLowerCase())),
    [systemVariables, searchQuery]
  )

  const totalSuggestions = filteredVariables.length + filteredSystemVariables.length

  // 初始化和外部值变化时更新编辑器
  React.useEffect(() => {
    const editor = editorRef.current
    if (!editor) {
      return
    }

    // 如果是内部更新触发的，跳过
    if (isInternalUpdateRef.current) {
      isInternalUpdateRef.current = false
      return
    }

    // 首次挂载或值变化时，更新编辑器内容
    if (!isMountedRef.current || value !== lastValueRef.current) {
      isMountedRef.current = true
      lastValueRef.current = value
      renderEditorContent(editor, value || '', variableMap)
    }
  }, [value, variableMap])

  // 处理输入变化
  const handleInput = React.useCallback(() => {
    if (isComposingRef.current) return
    
    const editor = editorRef.current
    if (!editor) return

    const newText = htmlToText(editor)
    
    if (newText !== lastValueRef.current) {
      lastValueRef.current = newText
      isInternalUpdateRef.current = true
      onChange(newText)
    }

    // 检查变量上下文
    const cursorPos = getCursorPosition(editor)
    const context = getVariableContext(newText, cursorPos)

    if (context.isInVariable) {
      setSearchQuery(context.query)
      setShowSuggestions(true)
      setSelectedIndex(0)
      variableStartPosRef.current = context.startPos

      // 计算建议框位置
      const selection = window.getSelection()
      if (selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        const containerRect = containerRef.current?.getBoundingClientRect()
        
        if (containerRect && rect.width >= 0) {
          setSuggestionPosition({
            top: rect.bottom - containerRect.top + 4,
            left: Math.max(0, Math.min(rect.left - containerRect.left, containerRect.width - 260)),
          })
        }
      }
    } else {
      setShowSuggestions(false)
      variableStartPosRef.current = -1
    }
  }, [onChange])

  // 插入变量
  const insertVariable = React.useCallback((varName: string) => {
    const editor = editorRef.current
    if (!editor || variableStartPosRef.current === -1) return

    const currentText = htmlToText(editor)
    const startPos = variableStartPosRef.current
    const cursorPos = getCursorPosition(editor)
    
    const textBefore = currentText.substring(0, startPos)
    const textAfter = currentText.substring(cursorPos)
    const newText = `${textBefore}{{${varName}}}${textAfter}`

    lastValueRef.current = newText
    isInternalUpdateRef.current = true
    onChange(newText)
    
    // 更新编辑器内容
    renderEditorContent(editor, newText, variableMap)
    
    // 设置光标位置到变量后面
    const newCursorPos = startPos + varName.length + 4
    setCursorPosition(editor, newCursorPos)
    
    setShowSuggestions(false)
    setSearchQuery('')
    variableStartPosRef.current = -1
    
    editor.focus()
  }, [onChange, variableMap])

  // 处理键盘事件
  const handleKeyDown = React.useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (showSuggestions && totalSuggestions > 0) {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex(prev => (prev + 1) % totalSuggestions)
          return
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex(prev => (prev - 1 + totalSuggestions) % totalSuggestions)
          return
        case 'Enter':
        case 'Tab':
          e.preventDefault()
          if (selectedIndex < filteredSystemVariables.length) {
            insertVariable(filteredSystemVariables[selectedIndex].name)
          } else {
            insertVariable(filteredVariables[selectedIndex - filteredSystemVariables.length].name)
          }
          return
        case 'Escape':
          e.preventDefault()
          setShowSuggestions(false)
          return
      }
    }
  }, [showSuggestions, totalSuggestions, filteredSystemVariables, filteredVariables, selectedIndex, insertVariable])

  // 点击外部关闭建议
  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        popoverRef.current && 
        !popoverRef.current.contains(e.target as Node) &&
        editorRef.current &&
        !editorRef.current.contains(e.target as Node)
      ) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 处理粘贴 - 只粘贴纯文本
  const handlePaste = React.useCallback((e: React.ClipboardEvent) => {
    e.preventDefault()
    const text = e.clipboardData.getData('text/plain')
    document.execCommand('insertText', false, text)
  }, [])

  return (
    <div ref={containerRef} className="relative">
      {/* 可编辑区域 */}
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        onCompositionStart={() => { isComposingRef.current = true }}
        onCompositionEnd={() => { 
          isComposingRef.current = false
          handleInput()
        }}
        data-placeholder={placeholder}
        className={cn(
          'min-h-50 w-full resize-none border-0 bg-transparent p-0 text-sm leading-relaxed',
          'focus:outline-none focus-visible:ring-0 shadow-none',
          'overflow-auto whitespace-pre-wrap',
          'empty:before:content-[attr(data-placeholder)] empty:before:text-muted-foreground empty:before:pointer-events-none',
          className
        )}
      />

      {/* 变量建议弹窗 */}
      {showSuggestions && (
        <div
          ref={popoverRef}
          className="absolute z-50 w-64 rounded-lg border bg-popover shadow-lg overflow-hidden"
          style={{ top: suggestionPosition.top, left: suggestionPosition.left }}
          onMouseDown={(e) => e.preventDefault()}
        >
          <ScrollArea className="max-h-48">
            <div className="p-1">
              {totalSuggestions > 0 ? (
                <>
                  {/* System Variables */}
                  {filteredSystemVariables.length > 0 && (
                    <>
                      <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                        {t('systemVariables')}
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
                            onMouseEnter={() => setSelectedIndex(index)}
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
                          {t('userVariables')}
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
                          onMouseEnter={() => setSelectedIndex(index + filteredSystemVariables.length)}
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
                    {searchQuery ? t('variableNotFound', { query: searchQuery }) : t('noVariables')}
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
                      {t('createVariable', { name: searchQuery })}
                    </Button>
                  )}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}

      {/* 未定义变量警告 */}
      {undefinedVars.length > 0 && (
        <div className="mt-3 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-amber-700 dark:text-amber-400 mb-2">
                {t('undefinedVariablesHint')}
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
