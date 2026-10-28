'use client'

import {
  useCallback,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type RefObject,
} from 'react'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

export interface VariableInputProps {
  value: string
  onChange: (value: string) => void
  variables: string[]
  placeholder?: string
  className?: string
  multiline?: boolean
  rows?: number
  suggestionTitle?: string
  id?: string
  ariaInvalid?: boolean
  type?: 'text' | 'password'
}

/**
 * Text input with `{{` completion for tool configuration fields.
 *
 * Candidates are tool parameter names and declared connection field names.
 * Only identifiers are shown; connection values are never read in the editor.
 */
export function VariableInput({
  value,
  onChange,
  variables,
  placeholder,
  className,
  multiline,
  rows = 4,
  suggestionTitle = '{{variable}}',
  id,
  ariaInvalid,
  type = 'text',
}: VariableInputProps) {
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [filteredVars, setFilteredVars] = useState<string[]>([])
  const [cursorPosition, setCursorPosition] = useState(0)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)

  // 检测是否正在输入变量
  const checkForVariableInput = useCallback(
    (text: string, pos: number) => {
      // 从光标位置向前查找 {{
      const beforeCursor = text.slice(0, pos)
      const lastOpenBrace = beforeCursor.lastIndexOf('{{')

      if (lastOpenBrace === -1) {
        setShowSuggestions(false)
        return
      }

      // 检查 {{ 后面是否已经有 }}
      const afterOpenBrace = text.slice(lastOpenBrace + 2, pos)
      if (afterOpenBrace.includes('}}')) {
        setShowSuggestions(false)
        return
      }

      // 获取已输入的变量名部分
      const partialVar = afterOpenBrace.toLowerCase()

      // 过滤匹配的变量
      const uniqueVariables = Array.from(new Set(variables.filter(Boolean)))
      const filtered = uniqueVariables.filter((variable) =>
        variable.toLowerCase().includes(partialVar)
      )

      if (filtered.length > 0) {
        setFilteredVars(filtered)
        setSelectedIndex(0)
        setShowSuggestions(true)
      } else {
        setShowSuggestions(false)
      }
    },
    [variables]
  )

  const insertVariable = (varName: string) => {
    const beforeCursor = value.slice(0, cursorPosition)
    const afterCursor = value.slice(cursorPosition)

    // 找到最后一个 {{ 的位置
    const lastOpenBrace = beforeCursor.lastIndexOf('{{')

    if (lastOpenBrace !== -1) {
      // 替换 {{ 后面已输入的内容
      const newValue =
        beforeCursor.slice(0, lastOpenBrace) + `{{${varName}}}` + afterCursor
      onChange(newValue)

      // 设置光标位置到 }} 后面
      const newPos = lastOpenBrace + varName.length + 4
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.setSelectionRange(newPos, newPos)
          inputRef.current.focus()
        }
      }, 0)
    }

    setShowSuggestions(false)
  }

  const handleChange = (
    event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const newValue = event.target.value
    const position = event.target.selectionStart || 0
    onChange(newValue)
    setCursorPosition(position)
    checkForVariableInput(newValue, position)
  }

  const handleKeyDown = (event: KeyboardEvent) => {
    if (!showSuggestions) return

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        setSelectedIndex((previous) =>
          Math.min(previous + 1, filteredVars.length - 1)
        )
        break
      case 'ArrowUp':
        event.preventDefault()
        setSelectedIndex((previous) => Math.max(previous - 1, 0))
        break
      case 'Enter':
      case 'Tab':
        if (filteredVars.length > 0) {
          event.preventDefault()
          insertVariable(filteredVars[selectedIndex])
        }
        break
      case 'Escape':
        setShowSuggestions(false)
        break
    }
  }

  const handleBlur = () => {
    // 延迟关闭，以便能点击建议项
    setTimeout(() => setShowSuggestions(false), 150)
  }

  const showDropdown = showSuggestions && filteredVars.length > 0

  const commonProps = {
    id,
    value,
    onChange: handleChange,
    onKeyDown: handleKeyDown,
    onBlur: handleBlur,
    placeholder,
    'aria-invalid': ariaInvalid || undefined,
    'aria-autocomplete': 'list' as const,
    'aria-expanded': showDropdown,
  }

  return (
    <div className={cn('relative', className)}>
      {multiline ? (
        <Textarea
          ref={inputRef as RefObject<HTMLTextAreaElement>}
          rows={rows}
          className="w-full"
          {...commonProps}
        />
      ) : (
        <Input
          ref={inputRef as RefObject<HTMLInputElement>}
          type={type}
          className="w-full"
          {...commonProps}
        />
      )}
      {showDropdown && (
        <div
          role="listbox"
          className="absolute left-0 top-full mt-1 z-50 w-48 rounded-md border bg-popover p-1 shadow-md"
        >
          <div className="text-xs text-muted-foreground px-2 py-1 border-b mb-1">
            {suggestionTitle}
          </div>
          {filteredVars.map((varName, index) => (
            <button
              key={varName}
              type="button"
              role="option"
              aria-selected={index === selectedIndex}
              className={cn(
                'w-full text-left px-2 py-1.5 text-sm rounded-sm',
                index === selectedIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-muted'
              )}
              onMouseDown={(event) => {
                event.preventDefault()
                insertVariable(varName)
              }}
              onMouseEnter={() => setSelectedIndex(index)}
            >
              <span className="font-mono text-primary">{`{{${varName}}}`}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
