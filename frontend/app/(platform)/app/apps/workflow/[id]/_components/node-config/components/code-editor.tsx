'use client'

import * as React from 'react'
import { useCallback, useState, useEffect, useRef, memo } from 'react'
import { createPortal } from 'react-dom'
import Editor, { Monaco } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'
import { useTheme } from 'next-themes'
import { Copy, Check, Maximize2, X, HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { CodeLanguage } from '../../nodes/code-node'

// 扩展语言类型，支持 jinja2
type EditorLanguage = CodeLanguage | 'jinja2'

interface CodeEditorProps {
  value: string
  language: EditorLanguage
  onChange: (value: string) => void
  onLanguageChange?: (language: CodeLanguage) => void
  className?: string
  minHeight?: number
  showLanguageSelector?: boolean  // 是否显示语言选择器，默认 true
}

// Monaco 编辑器配置选项
const editorOptions: editor.IStandaloneEditorConstructionOptions = {
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  fontSize: 12,
  lineNumbers: 'on',
  lineNumbersMinChars: 3,
  folding: true,
  wordWrap: 'on',
  automaticLayout: true,
  tabSize: 4,
  insertSpaces: true,
  renderWhitespace: 'selection',
  scrollbar: {
    vertical: 'auto',
    horizontal: 'auto',
    verticalScrollbarSize: 8,
    horizontalScrollbarSize: 8,
  },
  padding: { top: 8, bottom: 8 },
}

// 全屏模式下的编辑器配置
const fullscreenEditorOptions: editor.IStandaloneEditorConstructionOptions = {
  ...editorOptions,
  fontSize: 14,
  minimap: { enabled: true },
  lineNumbersMinChars: 4,
}

// Python 语法定义
const pythonLanguageDefinition = {
  defaultToken: '',
  tokenPostfix: '.python',
  keywords: [
    'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
    'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from',
    'global', 'if', 'import', 'in', 'is', 'lambda', 'None', 'nonlocal',
    'not', 'or', 'pass', 'raise', 'return', 'True', 'False', 'try',
    'while', 'with', 'yield',
  ],
  builtins: [
    'abs', 'all', 'any', 'bin', 'bool', 'bytearray', 'bytes', 'callable',
    'chr', 'classmethod', 'compile', 'complex', 'delattr', 'dict', 'dir',
    'divmod', 'enumerate', 'eval', 'exec', 'filter', 'float', 'format',
    'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'help', 'hex',
    'id', 'input', 'int', 'isinstance', 'issubclass', 'iter', 'len',
    'list', 'locals', 'map', 'max', 'memoryview', 'min', 'next', 'object',
    'oct', 'open', 'ord', 'pow', 'print', 'property', 'range', 'repr',
    'reversed', 'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod',
    'str', 'sum', 'super', 'tuple', 'type', 'vars', 'zip',
  ],
  tokenizer: {
    root: [
      [/#.*$/, 'comment'],
      [/"""/, 'string', '@string_triple'],
      [/'''/, 'string', '@string_triple_single'],
      [/"([^"\\]|\\.)*$/, 'string.invalid'],
      [/'([^'\\]|\\.)*$/, 'string.invalid'],
      [/"/, 'string', '@string_double'],
      [/'/, 'string', '@string_single'],
      [/[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?/, 'number'],
      [/\b(def|class)\b/, 'keyword', '@function_def'],
      [/[a-zA-Z_]\w*/, {
        cases: {
          '@keywords': 'keyword',
          '@builtins': 'type.identifier',
          '@default': 'identifier',
        },
      }],
      [/[{}()\[\]]/, '@brackets'],
      [/[<>]=?|[!=]=?|[-+*/%&|^~]/, 'operator'],
      [/[,;:]/, 'delimiter'],
    ],
    string_triple: [
      [/[^"]+/, 'string'],
      [/"""/, 'string', '@pop'],
      [/"/, 'string'],
    ],
    string_triple_single: [
      [/[^']+/, 'string'],
      [/'''/, 'string', '@pop'],
      [/'/, 'string'],
    ],
    string_double: [
      [/[^\\"]+/, 'string'],
      [/\\./, 'string.escape'],
      [/"/, 'string', '@pop'],
    ],
    string_single: [
      [/[^\\']+/, 'string'],
      [/\\./, 'string.escape'],
      [/'/, 'string', '@pop'],
    ],
    function_def: [
      [/\s+/, ''],
      [/[a-zA-Z_]\w*/, 'function', '@pop'],
      [/./, '@rematch', '@pop'],
    ],
  },
}

// Jinja2 语法定义
const jinja2LanguageDefinition = {
  defaultToken: '',
  tokenPostfix: '.jinja2',
  keywords: [
    'if', 'else', 'elif', 'endif', 'for', 'endfor', 'in', 'not', 'and', 'or',
    'block', 'endblock', 'extends', 'include', 'import', 'from', 'as',
    'macro', 'endmacro', 'call', 'endcall', 'filter', 'endfilter',
    'set', 'endset', 'raw', 'endraw', 'with', 'endwith', 'autoescape', 'endautoescape',
    'true', 'false', 'none', 'True', 'False', 'None',
  ],
  filters: [
    'abs', 'attr', 'batch', 'capitalize', 'center', 'default', 'd', 'dictsort',
    'escape', 'e', 'filesizeformat', 'first', 'float', 'forceescape', 'format',
    'groupby', 'indent', 'int', 'join', 'last', 'length', 'list', 'lower',
    'map', 'max', 'min', 'pprint', 'random', 'reject', 'rejectattr', 'replace',
    'reverse', 'round', 'safe', 'select', 'selectattr', 'slice', 'sort',
    'string', 'striptags', 'sum', 'title', 'trim', 'truncate', 'unique',
    'upper', 'urlencode', 'urlize', 'wordcount', 'wordwrap', 'xmlattr',
  ],
  tokenizer: {
    root: [
      // Jinja2 注释 {# ... #}
      [/\{#/, 'comment', '@comment'],
      // Jinja2 语句 {% ... %}
      [/\{%[-+]?/, 'keyword', '@statement'],
      // Jinja2 表达式 {{ ... }}
      [/\{\{[-+]?/, 'variable', '@expression'],
      // 普通文本
      [/[^{]+/, 'string'],
      [/\{/, 'string'],
    ],
    comment: [
      [/#\}/, 'comment', '@pop'],
      [/./, 'comment'],
    ],
    statement: [
      [/[-+]?%\}/, 'keyword', '@pop'],
      [/"([^"\\]|\\.)*"/, 'string'],
      [/'([^'\\]|\\.)*'/, 'string'],
      [/[0-9]+(\.[0-9]+)?/, 'number'],
      [/[a-zA-Z_]\w*/, {
        cases: {
          '@keywords': 'keyword',
          '@filters': 'type.identifier',
          '@default': 'identifier',
        },
      }],
      [/\|/, 'operator'],
      [/[=<>!]+/, 'operator'],
      [/[(),.\[\]]/, 'delimiter'],
      [/\s+/, ''],
    ],
    expression: [
      [/[-+]?\}\}/, 'variable', '@pop'],
      [/"([^"\\]|\\.)*"/, 'string'],
      [/'([^'\\]|\\.)*'/, 'string'],
      [/[0-9]+(\.[0-9]+)?/, 'number'],
      [/[a-zA-Z_]\w*/, {
        cases: {
          '@keywords': 'keyword',
          '@filters': 'type.identifier',
          '@default': 'variable',
        },
      }],
      [/\|/, 'operator'],
      [/[=<>!]+/, 'operator'],
      [/[(),.\[\]]/, 'delimiter'],
      [/\s+/, ''],
    ],
  },
}

function CodeEditorComponent({
  value,
  language,
  onChange,
  onLanguageChange,
  className,
  minHeight = 200,
  showLanguageSelector = true,
}: CodeEditorProps) {
  const { resolvedTheme } = useTheme()
  const [copied, setCopied] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [portalMounted, setPortalMounted] = useState(false)
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)
  const fullscreenEditorRef = useRef<editor.IStandaloneCodeEditor | null>(null)

  // 是否是 Jinja2 模式
  const isJinja2 = language === 'jinja2'

  // 复制代码
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      console.error('Failed to copy code')
    }
  }, [value])

  // ESC 键退出全屏
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false)
      }
    }

    if (isFullscreen) {
      document.addEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'hidden'
      return () => {
        document.removeEventListener('keydown', handleKeyDown)
        document.body.style.overflow = ''
      }
    }
  }, [isFullscreen])

  // Portal 挂载
  useEffect(() => {
    setPortalMounted(true)
  }, [])

  // Monaco 语言映射
  const monacoLanguage = isJinja2 ? 'jinja2' : (language === 'python' ? 'python' : 'javascript')

  // 处理 Monaco 编辑器加载
  const handleEditorMount = useCallback((editor: editor.IStandaloneCodeEditor, monaco: Monaco) => {
    editorRef.current = editor
    // 设置 Python 语法
    if (!monaco.languages.getLanguages().some((lang: { id: string; configured?: boolean }) => lang.id === 'python' && lang.configured)) {
      monaco.languages.setMonarchTokensProvider('python', pythonLanguageDefinition as never)
    }
    // 注册 Jinja2 语言
    if (!monaco.languages.getLanguages().some((lang: { id: string }) => lang.id === 'jinja2')) {
      monaco.languages.register({ id: 'jinja2' })
      monaco.languages.setMonarchTokensProvider('jinja2', jinja2LanguageDefinition as never)
    }
  }, [])

  // 处理全屏编辑器加载
  const handleFullscreenEditorMount = useCallback((editor: editor.IStandaloneCodeEditor, monaco: Monaco) => {
    fullscreenEditorRef.current = editor
    if (!monaco.languages.getLanguages().some((lang: { id: string; configured?: boolean }) => lang.id === 'python' && lang.configured)) {
      monaco.languages.setMonarchTokensProvider('python', pythonLanguageDefinition as never)
    }
    if (!monaco.languages.getLanguages().some((lang: { id: string }) => lang.id === 'jinja2')) {
      monaco.languages.register({ id: 'jinja2' })
      monaco.languages.setMonarchTokensProvider('jinja2', jinja2LanguageDefinition as never)
    }
  }, [])

  // 稳定的 onChange 处理
  const handleChange = useCallback((v: string | undefined) => {
    onChange(v || '')
  }, [onChange])

  const handleLanguageSelect = useCallback((v: CodeLanguage | null) => {
    if (v && onLanguageChange) onLanguageChange(v)
  }, [onLanguageChange])

  const openFullscreen = useCallback(() => setIsFullscreen(true), [])
  const closeFullscreen = useCallback(() => setIsFullscreen(false), [])

  return (
    <>
      {/* 普通模式编辑器 */}
      <div className={cn('rounded-lg border bg-muted/30 overflow-hidden', className)}>
        {/* 工具栏 */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b bg-muted/50">
          {showLanguageSelector && !isJinja2 ? (
            <Select value={language as CodeLanguage} onValueChange={handleLanguageSelect}>
              <SelectTrigger className="h-7 w-28 text-xs font-medium border-0 bg-transparent shadow-none">
                <SelectValue>
                  {language === 'python' ? 'Python' : 'JavaScript'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="python" className="text-xs">Python</SelectItem>
                <SelectItem value="javascript" className="text-xs">JavaScript</SelectItem>
              </SelectContent>
            </Select>
          ) : isJinja2 ? (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>只支持 Jinja2</span>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger
                    render={<HelpCircle className="h-3 w-3 cursor-help" />}
                  />
                  <TooltipContent side="right" className="max-w-60">
                    <p className="text-xs">
                      Jinja2 是一种模板语言，使用 {'{{ 变量名 }}'} 语法引用变量。
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          ) : (
            <div className="text-xs font-medium text-muted-foreground">
              {language === 'python' ? 'Python' : 'JavaScript'}
            </div>
          )}
          
          <div className="flex items-center gap-1">
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-6 w-6"
              onClick={handleCopy}
            >
              {copied ? (
                <Check className="h-3 w-3 text-green-500" />
              ) : (
                <Copy className="h-3 w-3 text-muted-foreground" />
              )}
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-6 w-6"
              onClick={openFullscreen}
            >
              <Maximize2 className="h-3 w-3 text-muted-foreground" />
            </Button>
          </div>
        </div>
        
        {/* Monaco 编辑器 */}
        <Editor
          height={minHeight}
          language={monacoLanguage}
          value={value}
          onChange={handleChange}
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          options={editorOptions}
          onMount={handleEditorMount}
          loading={
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              加载编辑器...
            </div>
          }
        />
      </div>

      {/* 全屏模式编辑器 - 使用 Portal 渲染到 body */}
      {isFullscreen && portalMounted && createPortal(
        <div className="fixed inset-0 z-9999 bg-background flex flex-col">
          {/* 顶部工具栏 */}
          <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/50">
            <div className="flex items-center gap-3">
              <h2 className="text-base font-medium">
                {isJinja2 ? '模板编辑器' : '代码编辑器'}
              </h2>
              {showLanguageSelector && !isJinja2 ? (
                <Select value={language as CodeLanguage} onValueChange={handleLanguageSelect}>
                  <SelectTrigger className="h-8 w-32 text-sm font-medium">
                    <SelectValue>
                      {language === 'python' ? 'Python' : 'JavaScript'}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="python" className="text-sm">Python</SelectItem>
                    <SelectItem value="javascript" className="text-sm">JavaScript</SelectItem>
                  </SelectContent>
                </Select>
              ) : isJinja2 ? (
                <span className="text-sm text-muted-foreground">Jinja2</span>
              ) : (
                <span className="text-sm font-medium">
                  {language === 'python' ? 'Python' : 'JavaScript'}
                </span>
              )}
              <span className="text-xs text-muted-foreground">
                按 ESC 退出全屏
              </span>
            </div>
            
            <div className="flex items-center gap-2">
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-8 w-8"
                onClick={handleCopy}
              >
                {copied ? (
                  <Check className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-8 w-8"
                onClick={closeFullscreen}
              >
                <X className="h-4 w-4 text-muted-foreground" />
              </Button>
            </div>
          </div>
          
          {/* Monaco 编辑器 */}
          <div className="flex-1">
            <Editor
              height="100%"
              language={monacoLanguage}
              value={value}
              onChange={handleChange}
              theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
              options={fullscreenEditorOptions}
              onMount={handleFullscreenEditorMount}
              loading={
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  加载编辑器...
                </div>
              }
            />
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

export const CodeEditor = memo(CodeEditorComponent)
