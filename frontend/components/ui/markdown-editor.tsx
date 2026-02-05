'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTheme } from 'next-themes'
import { cn } from '@/lib/utils'

// 动态导入避免 SSR 问题
const MDEditor = dynamic(() => import('@uiw/react-md-editor'), { ssr: false })

interface MarkdownEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  height?: number
  className?: string
  preview?: 'edit' | 'live' | 'preview'
}

export function MarkdownEditor({
  value,
  onChange,
  placeholder,
  height = 200,
  className,
  preview = 'live',
}: MarkdownEditorProps) {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  // 避免 hydration 问题
  const colorMode = mounted ? (resolvedTheme === 'dark' ? 'dark' : 'light') : 'light'

  return (
    <div className={cn('markdown-editor rounded-lg border border-border overflow-hidden', className)} data-color-mode={colorMode}>
      <MDEditor
        value={value}
        onChange={(val) => onChange(val || '')}
        preview={preview}
        height={height}
        textareaProps={{
          placeholder,
        }}
        previewOptions={{
          style: {
            backgroundColor: 'transparent',
          },
        }}
      />
      <style jsx global>{`
        .markdown-editor .w-md-editor {
          border-radius: 0 !important;
          border: none !important;
          background-color: hsl(var(--background));
          box-shadow: none !important;
        }
        .markdown-editor .w-md-editor-toolbar {
          border-bottom: 1px solid hsl(var(--border));
          background-color: hsl(var(--muted));
          border-radius: 0.5rem 0.5rem 0 0;
        }
        .markdown-editor .w-md-editor-toolbar li > button {
          color: hsl(var(--foreground));
        }
        .markdown-editor .w-md-editor-toolbar li > button:hover {
          background-color: hsl(var(--accent));
        }
        .markdown-editor .w-md-editor-toolbar li.active > button {
          background-color: hsl(var(--accent));
        }
        .markdown-editor .w-md-editor-content {
          background-color: hsl(var(--background));
        }
        .markdown-editor .w-md-editor-text-pre > code,
        .markdown-editor .w-md-editor-text-input {
          font-size: 14px !important;
          line-height: 1.6 !important;
          color: hsl(var(--foreground)) !important;
        }
        .markdown-editor .w-md-editor-text-input::placeholder {
          color: hsl(var(--muted-foreground)) !important;
        }
        .markdown-editor .w-md-editor-text {
          background-color: hsl(var(--background));
        }
        .markdown-editor .w-md-editor-area {
          background-color: hsl(var(--background));
        }
        .markdown-editor .wmde-markdown {
          background-color: transparent !important;
          font-size: 14px;
          color: hsl(var(--foreground));
        }
        .markdown-editor .wmde-markdown hr {
          border-color: hsl(var(--border));
        }
        .markdown-editor .wmde-markdown code {
          background-color: hsl(var(--muted));
          color: hsl(var(--foreground));
        }
        .markdown-editor .wmde-markdown pre {
          background-color: hsl(var(--muted)) !important;
        }
        .markdown-editor .wmde-markdown blockquote {
          border-left-color: hsl(var(--border));
          color: hsl(var(--muted-foreground));
        }
        .markdown-editor .wmde-markdown a {
          color: hsl(var(--primary));
        }
        .markdown-editor .wmde-markdown table tr {
          background-color: hsl(var(--background));
          border-color: hsl(var(--border));
        }
        .markdown-editor .wmde-markdown table tr:nth-child(2n) {
          background-color: hsl(var(--muted) / 0.5);
        }
        .markdown-editor .wmde-markdown table th,
        .markdown-editor .wmde-markdown table td {
          border-color: hsl(var(--border));
        }
        .markdown-editor .w-md-editor-preview {
          background-color: hsl(var(--muted) / 0.3);
        }
        .markdown-editor .w-md-editor-content {
          border-bottom-left-radius: 0.5rem;
          border-bottom-right-radius: 0.5rem;
          overflow: hidden;
          position: relative;
        }
        /* 编辑区和预览区之间的分割线 - 使用伪元素 */
        .markdown-editor .w-md-editor-show-live .w-md-editor-content::before {
          content: '';
          position: absolute;
          top: 0;
          bottom: 0;
          left: 50%;
          width: 1px;
          background-color: hsl(var(--border));
          z-index: 10;
        }
        .markdown-editor .w-md-editor-bar {
          background-color: hsl(var(--muted));
        }
        .markdown-editor .w-md-editor-bar svg {
          color: hsl(var(--muted-foreground));
        }
      `}</style>
    </div>
  )
}
