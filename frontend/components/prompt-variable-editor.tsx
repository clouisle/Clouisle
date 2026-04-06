'use client'

import * as React from 'react'
import { AlertCircle, Plus, Variable } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

export interface PromptVariableItem {
  ref: string
  name: string
  label?: string
  groupId?: string
  groupLabel?: string
  isSystem?: boolean
  type?: string
  icon?: React.ElementType
}

type GroupMode = 'flat' | 'system-user' | 'custom'

interface PromptVariableEditorProps {
  value: string
  onChange: (value: string) => void
  variables: PromptVariableItem[]
  placeholder?: string
  className?: string
  editorClassName?: string
  minHeightClassName?: string
  groupMode?: GroupMode
  allowCreateVariable?: boolean
  onCreateVariable?: (ref: string) => void
  showUndefinedWarnings?: boolean
  onUndefinedVariableClick?: (ref: string) => void
  systemGroupLabel?: string
  userGroupLabel?: string
  noVariablesText?: string
  variableNotFoundText?: (query: string) => string
  createVariableText?: (name: string) => string
  undefinedVariablesHintText?: string
}

const VARIABLE_TOKEN_REGEX = /(\{\{[\w.-]+\}\})/g
const VARIABLE_REFERENCE_REGEX = /\{\{([\w.-]+)\}\}/g
const BLOCK_ELEMENTS = new Set(['DIV', 'P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'PRE'])

function parseVariableReferences(text: string): string[] {
  const matches: string[] = []
  let match: RegExpExecArray | null

  while ((match = VARIABLE_REFERENCE_REGEX.exec(text)) !== null) {
    if (!matches.includes(match[1])) {
      matches.push(match[1])
    }
  }

  return matches
}

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

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .replace(/\n/g, '<br>')
}

function textToHtml(text: string, variableMap: Map<string, PromptVariableItem>): string {
  if (!text) return ''

  let result = ''
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = VARIABLE_TOKEN_REGEX.exec(text)) !== null) {
    if (match.index > lastIndex) {
      result += escapeHtml(text.substring(lastIndex, match.index))
    }

    const ref = match[1].slice(2, -2)
    const variable = variableMap.get(ref)
    const tagClass = variable
      ? 'bg-primary/15 text-primary border-primary/20'
      : 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20'
    const displayName = escapeHtml(variable?.name || ref)
    const displayLabel = variable?.label ? escapeHtml(variable.label) : ''

    result += `\u200B<span class="variable-tag inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded text-[11px] font-medium border align-middle ${tagClass}" contenteditable="false" data-variable="${escapeHtml(ref)}">`
    result += '<span class="opacity-60 text-[10px]">{x}</span>'
    result += `<span>${displayName}</span>`
    if (displayLabel) {
      result += `<span class="opacity-70 text-[10px]">${displayLabel}</span>`
    }
    result += '</span>\u200B'

    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    result += escapeHtml(text.substring(lastIndex))
  }

  return result
}

function setSafeInnerHTML(element: HTMLElement, html: string): void {
  element.innerHTML = html
}

function htmlToText(element: HTMLElement): string {
  const parts: string[] = []

  const appendText = (text: string) => {
    if (!text) return
    parts.push(text)
  }

  const endsWithNewline = () => {
    if (parts.length === 0) return false
    return parts[parts.length - 1].endsWith('\n')
  }

  element.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      appendText((node.textContent || '').replace(/\u200B/g, ''))
      return
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
      return
    }

    const el = node as HTMLElement
    const variableRef = el.getAttribute('data-variable')

    if (variableRef) {
      appendText(`{{${variableRef}}}`)
      return
    }

    if (el.tagName === 'BR') {
      appendText('\n')
      return
    }

    if (BLOCK_ELEMENTS.has(el.tagName) && parts.length > 0 && !endsWithNewline()) {
      appendText('\n')
    }

    const childText = htmlToText(el)

    if (!childText && BLOCK_ELEMENTS.has(el.tagName)) {
      appendText('\n')
      return
    }

    appendText(childText)
  })

  return parts.join('')
}

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
      pos += (node.textContent || '').replace(/\u200B/g, '').length
      return false
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
      return false
    }

    const el = node as HTMLElement
    const variableRef = el.getAttribute?.('data-variable')
    if (variableRef) {
      if (range.startContainer === el || el.contains(range.startContainer)) {
        found = true
        return true
      }
      pos += variableRef.length + 4
      return false
    }

    if (el.tagName === 'BR') {
      pos += 1
      return false
    }

    for (const child of Array.from(node.childNodes)) {
      if (traverse(child)) return true
    }

    return false
  }

  traverse(containerEl)
  return pos
}

function setCursorPosition(containerEl: HTMLElement, targetPos: number): void {
  let currentPos = 0

  const traverse = (node: Node): { node: Node; offset: number } | null => {
    if (node.nodeType === Node.TEXT_NODE) {
      const textLength = (node.textContent || '').replace(/\u200B/g, '').length
      if (currentPos + textLength >= targetPos) {
        return { node, offset: targetPos - currentPos }
      }
      currentPos += textLength
      return null
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null
    }

    const el = node as HTMLElement
    const variableRef = el.getAttribute?.('data-variable')
    if (variableRef) {
      const variableLength = variableRef.length + 4
      if (currentPos + variableLength >= targetPos) {
        const parent = el.parentNode
        if (parent) {
          const index = Array.from(parent.childNodes).indexOf(el as ChildNode)
          return { node: parent, offset: index + 1 }
        }
      }
      currentPos += variableLength
      return null
    }

    if (el.tagName === 'BR') {
      if (currentPos + 1 >= targetPos) {
        const parent = el.parentNode
        if (parent) {
          const index = Array.from(parent.childNodes).indexOf(el as ChildNode)
          return { node: parent, offset: index + 1 }
        }
      }
      currentPos += 1
      return null
    }

    for (const child of Array.from(node.childNodes)) {
      const result = traverse(child)
      if (result) return result
    }

    return null
  }

  const result = traverse(containerEl)
  if (!result) return

  const selection = window.getSelection()
  if (!selection) return

  const range = document.createRange()
  range.setStart(result.node, result.offset)
  range.collapse(true)
  selection.removeAllRanges()
  selection.addRange(range)
}

export function PromptVariableEditor({
  value,
  onChange,
  variables,
  placeholder,
  className,
  editorClassName,
  minHeightClassName = 'min-h-20',
  groupMode = 'flat',
  allowCreateVariable = false,
  onCreateVariable,
  showUndefinedWarnings = false,
  onUndefinedVariableClick,
  systemGroupLabel,
  userGroupLabel,
  noVariablesText,
  variableNotFoundText,
  createVariableText,
  undefinedVariablesHintText,
}: PromptVariableEditorProps) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const editorRef = React.useRef<HTMLDivElement>(null)
  const popoverRef = React.useRef<HTMLDivElement>(null)
  const suggestionListRef = React.useRef<HTMLDivElement>(null)
  const [showSuggestions, setShowSuggestions] = React.useState(false)
  const [suggestionPosition, setSuggestionPosition] = React.useState({ top: 0, left: 0 })
  const [searchQuery, setSearchQuery] = React.useState('')
  const [selectedIndex, setSelectedIndex] = React.useState(0)
  const variableStartPosRef = React.useRef(-1)
  const isComposingRef = React.useRef(false)
  const isInternalUpdateRef = React.useRef(false)
  const [isInitialized, setIsInitialized] = React.useState(false)
  const lastValueRef = React.useRef(value)

  const variableMap = React.useMemo(() => {
    const map = new Map<string, PromptVariableItem>()
    variables.forEach((variable) => map.set(variable.ref, variable))
    return map
  }, [variables])

  const filteredVariables = React.useMemo(() => {
    if (!searchQuery) return variables

    const query = searchQuery.toLowerCase()
    return variables.filter((variable) =>
      variable.name.toLowerCase().includes(query) ||
      variable.ref.toLowerCase().includes(query) ||
      variable.label?.toLowerCase().includes(query) ||
      variable.groupLabel?.toLowerCase().includes(query)
    )
  }, [variables, searchQuery])

  const suggestionGroups = React.useMemo(() => {
    if (groupMode === 'flat') {
      return [{ id: 'all', label: '', items: filteredVariables }]
    }

    if (groupMode === 'system-user') {
      const systemItems = filteredVariables.filter((item) => item.isSystem)
      const userItems = filteredVariables.filter((item) => !item.isSystem)
      return [
        systemItems.length > 0 ? { id: 'system', label: systemGroupLabel || '', items: systemItems } : null,
        userItems.length > 0 ? { id: 'user', label: userGroupLabel || '', items: userItems } : null,
      ].filter(Boolean) as Array<{ id: string; label: string; items: PromptVariableItem[] }>
    }

    const groups = filteredVariables.reduce((acc, variable) => {
      const id = variable.groupId || 'default'
      if (!acc[id]) {
        acc[id] = {
          id,
          label: variable.groupLabel || '',
          isSystem: Boolean(variable.isSystem),
          items: [],
        }
      }
      acc[id].items.push(variable)
      return acc
    }, {} as Record<string, { id: string; label: string; isSystem: boolean; items: PromptVariableItem[] }>)

    return Object.values(groups).sort((a, b) => {
      if (a.isSystem && !b.isSystem) return 1
      if (!a.isSystem && b.isSystem) return -1
      return 0
    })
  }, [filteredVariables, groupMode, systemGroupLabel, userGroupLabel])

  const flatSuggestions = React.useMemo(() => suggestionGroups.flatMap((group) => group.items), [suggestionGroups])

  const undefinedVariables = React.useMemo(() => {
    if (!showUndefinedWarnings) return []
    const referencedVariables = parseVariableReferences(value)
    return referencedVariables.filter((ref) => !variableMap.has(ref))
  }, [showUndefinedWarnings, value, variableMap])

  React.useEffect(() => {
    const editor = editorRef.current
    if (!editor) return

    if (isInternalUpdateRef.current) {
      isInternalUpdateRef.current = false
      return
    }

    if (!isInitialized || value !== lastValueRef.current) {
      lastValueRef.current = value
      setSafeInnerHTML(editor, textToHtml(value || '', variableMap))
      if (!isInitialized) {
        setIsInitialized(true)
      }
    }
  }, [value, variableMap, isInitialized])

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

    const cursorPos = getCursorPosition(editor)
    const context = getVariableContext(newText, cursorPos)

    if (!context.isInVariable) {
      setShowSuggestions(false)
      variableStartPosRef.current = -1
      return
    }

    setSearchQuery(context.query)
    setShowSuggestions(true)
    setSelectedIndex(0)
    variableStartPosRef.current = context.startPos

    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0) return

    const range = selection.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    const containerRect = containerRef.current?.getBoundingClientRect()

    if (containerRect && rect.width >= 0) {
      setSuggestionPosition({
        top: rect.bottom - containerRect.top + 4,
        left: Math.max(0, Math.min(rect.left - containerRect.left, containerRect.width - 260)),
      })
    }
  }, [onChange])

  const insertVariable = React.useCallback((variable: PromptVariableItem) => {
    const editor = editorRef.current
    if (!editor || variableStartPosRef.current === -1) return

    const currentText = htmlToText(editor)
    const startPos = variableStartPosRef.current
    const cursorPos = getCursorPosition(editor)
    const newText = `${currentText.substring(0, startPos)}{{${variable.ref}}}${currentText.substring(cursorPos)}`

    lastValueRef.current = newText
    isInternalUpdateRef.current = true
    onChange(newText)

    setSafeInnerHTML(editor, textToHtml(newText, variableMap))
    setCursorPosition(editor, startPos + variable.ref.length + 4)

    setShowSuggestions(false)
    setSearchQuery('')
    variableStartPosRef.current = -1
    editor.focus()
  }, [onChange, variableMap])

  const handleKeyDown = React.useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!showSuggestions || flatSuggestions.length === 0) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex((prev) => (prev + 1) % flatSuggestions.length)
        return
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex((prev) => (prev - 1 + flatSuggestions.length) % flatSuggestions.length)
        return
      case 'Enter':
      case 'Tab':
        e.preventDefault()
        insertVariable(flatSuggestions[selectedIndex])
        return
      case 'Escape':
        e.preventDefault()
        setShowSuggestions(false)
        return
    }
  }, [flatSuggestions, insertVariable, selectedIndex, showSuggestions])

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

  React.useEffect(() => {
    if (!showSuggestions) return

    const list = suggestionListRef.current
    if (!list) return

    const selectedItem = list.querySelector<HTMLElement>(`[data-suggestion-index="${selectedIndex}"]`)
    selectedItem?.scrollIntoView({ block: 'nearest' })
  }, [selectedIndex, showSuggestions])

  const handlePaste = React.useCallback((e: React.ClipboardEvent) => {
    e.preventDefault()
    const text = e.clipboardData.getData('text/plain')
    document.execCommand('insertText', false, text)
  }, [])

  const canCreateVariable = allowCreateVariable && !!searchQuery && typeof onCreateVariable === 'function'

  return (
    <div className={cn('relative', className)} ref={containerRef}>
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
          'w-full resize-none overflow-auto whitespace-pre-wrap',
          'focus:outline-none',
          'empty:before:content-[attr(data-placeholder)] empty:before:text-muted-foreground empty:before:pointer-events-none',
          minHeightClassName,
          editorClassName
        )}
      />

      {showSuggestions && (
        <div
          ref={popoverRef}
          className="absolute z-50 w-64 rounded-lg border bg-popover shadow-lg overflow-hidden"
          style={{ top: suggestionPosition.top, left: suggestionPosition.left }}
        >
          <div
            ref={suggestionListRef}
            className="max-h-48 overflow-y-auto overscroll-contain p-1"
            onMouseDown={(e) => e.stopPropagation()}
            onWheel={(e) => e.stopPropagation()}
          >
            {flatSuggestions.length > 0 ? (
              suggestionGroups.map((group) => {
                if (group.items.length === 0) return null

                return (
                  <div key={group.id} className="mb-1 last:mb-0">
                    {group.label ? (
                      <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                        {group.label}
                      </div>
                    ) : null}
                    {group.items.map((variable) => {
                      const index = flatSuggestions.indexOf(variable)
                      const Icon = variable.icon || Variable

                      return (
                        <button
                          key={variable.ref}
                          type="button"
                          data-suggestion-index={index}
                          className={cn(
                            'w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-sm transition-colors cursor-pointer',
                            index === selectedIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'
                          )}
                          onMouseDown={(e) => {
                            e.preventDefault()
                            insertVariable(variable)
                          }}
                          onMouseEnter={() => setSelectedIndex(index)}
                        >
                          <Icon className={cn('h-3.5 w-3.5 shrink-0', variable.isSystem ? 'text-cyan-500' : 'text-blue-500')} />
                          <span className="font-mono text-xs truncate">{variable.name}</span>
                          {variable.label ? (
                            <span className="text-xs text-muted-foreground truncate flex-1">{variable.label}</span>
                          ) : (
                            <span className="flex-1" />
                          )}
                          {variable.type ? (
                            <span className="text-[10px] text-muted-foreground shrink-0">{variable.type}</span>
                          ) : null}
                        </button>
                      )
                    })}
                  </div>
                )
              })
            ) : (
              <div className="px-2 py-3 text-center">
                <p className="text-xs text-muted-foreground mb-2">
                  {searchQuery ? variableNotFoundText?.(searchQuery) || noVariablesText : noVariablesText}
                </p>
                {canCreateVariable ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onMouseDown={(e) => {
                      e.preventDefault()
                      onCreateVariable?.(searchQuery)
                    }}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    {createVariableText?.(searchQuery) || searchQuery}
                  </Button>
                ) : null}
              </div>
            )}
          </div>
        </div>
      )}

      {showUndefinedWarnings && undefinedVariables.length > 0 ? (
        <div className="mt-3 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              {undefinedVariablesHintText ? (
                <p className="text-xs text-amber-700 dark:text-amber-400 mb-2">
                  {undefinedVariablesHintText}
                </p>
              ) : null}
              <div className="flex flex-wrap gap-1.5">
                {undefinedVariables.map((ref) => (
                  <Button
                    key={ref}
                    variant="outline"
                    size="sm"
                    className="h-6 text-xs px-2 bg-background hover:bg-amber-500/10 border-amber-500/30 cursor-pointer"
                    onClick={() => onUndefinedVariableClick?.(ref)}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    {`{{${ref}}}`}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
