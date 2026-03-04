'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { AvailableVariable } from '../types'

interface PromptTextareaProps {
  value: string
  onChange: (value: string) => void
  variables: AvailableVariable[]
  placeholder?: string
  className?: string
  minHeight?: string
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

// HTML 转义（包括属性安全）
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .replace(/\n/g, '<br>')
}

// 将纯文本转换为带有变量标签的 HTML
// Note: All user input is sanitized via escapeHtml() before being included in the HTML
function textToHtml(text: string, variableMap: Map<string, AvailableVariable>): string {
  if (!text) return ''

  const regex = /(\{\{[\w.\-]+\}\})/g
  let result = ''
  let lastIndex = 0
  let match

  while ((match = regex.exec(text)) !== null) {
    // 添加变量之前的普通文本 (escaped for XSS protection)
    if (match.index > lastIndex) {
      result += escapeHtml(text.substring(lastIndex, match.index))
    }

    // 添加变量标签
    const varId = match[1].slice(2, -2)
    const variable = variableMap.get(varId)

    const tagClass = variable
      ? 'bg-primary/15 text-primary border-primary/20'
      : 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20'

    // 显示格式: {x}变量名 节点名
    const displayLabel = variable?.groupLabel
    // Escape variable name and label to prevent XSS
    const displayName = escapeHtml(variable?.name || varId)
    const escapedLabel = displayLabel ? escapeHtml(displayLabel) : ''

    result += `<span class="variable-tag inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded text-[11px] font-medium border align-middle ${tagClass}" contenteditable="false" data-variable="${escapeHtml(varId)}">`
    result += `<span class="opacity-60 text-[10px]">{x}</span>`
    result += `<span>${displayName}</span>`
    if (escapedLabel) {
      result += `<span class="opacity-70 text-[10px]">${escapedLabel}</span>`
    }
    result += `</span>`

    lastIndex = match.index + match[0].length
  }

  // 添加剩余的普通文本 (escaped for XSS protection)
  if (lastIndex < text.length) {
    result += escapeHtml(text.substring(lastIndex))
  }

  return result
}

// Safe wrapper for setting innerHTML with sanitized content
// lgtm[js/xss] - All user input is escaped via escapeHtml()
function setSafeInnerHTML(element: HTMLElement, html: string): void {
  // eslint-disable-next-line no-param-reassign
  element.innerHTML = html
}

// 将 HTML 转换回纯文本
function htmlToText(element: HTMLElement): string {
  let result = ''
  
  element.childNodes.forEach(node => {
    if (node.nodeType === Node.TEXT_NODE) {
      result += node.textContent || ''
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node as HTMLElement
      const varId = el.getAttribute('data-variable')
      if (varId) {
        result += `{{${varId}}}`
      } else if (el.tagName === 'BR') {
        result += '\n'
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
      const varId = el.getAttribute?.('data-variable')
      if (varId) {
        if (range.startContainer === el || el.contains(range.startContainer)) {
          found = true
          return true
        }
        pos += varId.length + 4 // {{varId}}
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
      const varId = el.getAttribute?.('data-variable')
      if (varId) {
        const varLen = varId.length + 4
        if (currentPos + varLen >= targetPos) {
          // 光标放在变量标签后面
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

export function PromptTextarea({
  value,
  onChange,
  variables,
  placeholder,
  className,
  minHeight = 'min-h-20',
}: PromptTextareaProps) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const editorRef = React.useRef<HTMLDivElement>(null)
  const popoverRef = React.useRef<HTMLDivElement>(null)
  const [showSuggestions, setShowSuggestions] = React.useState(false)
  const [suggestionPosition, setSuggestionPosition] = React.useState({ top: 0, left: 0 })
  const [searchQuery, setSearchQuery] = React.useState('')
  const [selectedIndex, setSelectedIndex] = React.useState(0)
  const variableStartPosRef = React.useRef(-1)
  const isComposingRef = React.useRef(false)
  const lastValueRef = React.useRef(value)
  const isInternalUpdateRef = React.useRef(false)

  // 构建变量ID到变量对象的映射
  const variableMap = React.useMemo(() => {
    const map = new Map<string, AvailableVariable>()
    variables.forEach(v => map.set(v.id, v))
    return map
  }, [variables])

  // 按 group 分组变量
  const groupedVariables = React.useMemo(() => {
    const groups = variables.reduce((acc, v) => {
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
  }, [variables])

  // 过滤变量
  const filteredVariables = React.useMemo(() => {
    if (!searchQuery) return variables
    return variables.filter(v => 
      v.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      v.id.toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [variables, searchQuery])

  // 初始化和外部值变化时更新编辑器
  const [isInitialized, setIsInitialized] = React.useState(false)
  
  React.useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    
    if (isInternalUpdateRef.current) {
      isInternalUpdateRef.current = false
      return
    }
    
    // 首次初始化或值变化时更新
    if (!isInitialized || value !== lastValueRef.current) {
      lastValueRef.current = value
      const html = textToHtml(value || '', variableMap)
      setSafeInnerHTML(editor, html || '')
      if (!isInitialized) {
        setIsInitialized(true)
      }
    }
  }, [value, variableMap, isInitialized])

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
            left: Math.max(0, Math.min(rect.left - containerRect.left, containerRect.width - 220)),
          })
        }
      }
    } else {
      setShowSuggestions(false)
      variableStartPosRef.current = -1
    }
  }, [onChange])

  // 插入变量
  const insertVariable = React.useCallback((variable: AvailableVariable) => {
    const editor = editorRef.current
    if (!editor || variableStartPosRef.current === -1) return

    const currentText = htmlToText(editor)
    const startPos = variableStartPosRef.current
    const cursorPos = getCursorPosition(editor)
    
    const textBefore = currentText.substring(0, startPos)
    const textAfter = currentText.substring(cursorPos)
    const newText = `${textBefore}{{${variable.id}}}${textAfter}`

    lastValueRef.current = newText
    isInternalUpdateRef.current = true
    onChange(newText)

    // 更新编辑器内容
    const html = textToHtml(newText, variableMap)
    setSafeInnerHTML(editor, html)

    // 设置光标位置到变量后面
    const newCursorPos = startPos + variable.id.length + 4
    setCursorPosition(editor, newCursorPos)
    
    setShowSuggestions(false)
    setSearchQuery('')
    variableStartPosRef.current = -1
    
    editor.focus()
  }, [onChange, variableMap])

  // 处理键盘事件
  const handleKeyDown = React.useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (showSuggestions && filteredVariables.length > 0) {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex(prev => (prev + 1) % filteredVariables.length)
          return
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex(prev => (prev - 1 + filteredVariables.length) % filteredVariables.length)
          return
        case 'Enter':
        case 'Tab':
          e.preventDefault()
          insertVariable(filteredVariables[selectedIndex])
          return
        case 'Escape':
          e.preventDefault()
          setShowSuggestions(false)
          return
      }
    }
  }, [showSuggestions, filteredVariables, selectedIndex, insertVariable])

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
          'w-full resize-none text-xs p-3 rounded-md border border-input bg-background',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
          'overflow-auto whitespace-pre-wrap',
          'empty:before:content-[attr(data-placeholder)] empty:before:text-muted-foreground empty:before:pointer-events-none',
          minHeight,
          className
        )}
      />

      {/* 变量建议弹窗 */}
      {showSuggestions && filteredVariables.length > 0 && (
        <div
          ref={popoverRef}
          className="absolute z-50 bg-popover border border-border rounded-md shadow-lg overflow-hidden"
          style={{
            top: suggestionPosition.top,
            left: suggestionPosition.left,
            minWidth: '200px',
            maxWidth: '280px',
          }}
        >
          <ScrollArea className="max-h-48">
            <div className="p-1">
              {groupedVariables.map(([groupId, group]) => {
                const groupItems = group.items.filter(v => filteredVariables.includes(v))
                if (groupItems.length === 0) return null
                
                return (
                  <div key={groupId} className="mb-1">
                    <div className="px-2 py-1 text-[10px] text-muted-foreground font-medium">
                      {group.label}
                    </div>
                    {groupItems.map((variable) => {
                      const index = filteredVariables.indexOf(variable)
                      return (
                        <button
                          key={variable.id}
                          className={cn(
                            'w-full px-2 py-1.5 text-left text-xs rounded-sm flex items-center gap-2',
                            'hover:bg-accent hover:text-accent-foreground',
                            index === selectedIndex && 'bg-accent text-accent-foreground'
                          )}
                          onClick={() => insertVariable(variable)}
                          onMouseEnter={() => setSelectedIndex(index)}
                        >
                          <span className="text-primary/70 font-mono text-[10px]">{'{x}'}</span>
                          <span className="truncate flex-1">{variable.name}</span>
                          <span className="text-[10px] text-muted-foreground">{variable.type}</span>
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  )
}
