'use client'

import * as React from 'react'
import { NodeProps, NodeResizer, useReactFlow } from '@xyflow/react'
import { Streamdown } from 'streamdown'
import { cn } from '@/lib/utils'

// 便签颜色配置
export const COMMENT_COLORS = {
  amber: {
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-800',
    borderSelected: 'border-amber-400',
    resizeLine: '!border-amber-300',
    resizeHandle: '!bg-amber-400',
    dot: 'bg-amber-300',
  },
  yellow: {
    bg: 'bg-yellow-50 dark:bg-yellow-950/30',
    border: 'border-yellow-200 dark:border-yellow-800',
    borderSelected: 'border-yellow-400',
    resizeLine: '!border-yellow-300',
    resizeHandle: '!bg-yellow-400',
    dot: 'bg-yellow-300',
  },
  lime: {
    bg: 'bg-lime-50 dark:bg-lime-950/30',
    border: 'border-lime-200 dark:border-lime-800',
    borderSelected: 'border-lime-400',
    resizeLine: '!border-lime-300',
    resizeHandle: '!bg-lime-400',
    dot: 'bg-lime-300',
  },
  green: {
    bg: 'bg-green-50 dark:bg-green-950/30',
    border: 'border-green-200 dark:border-green-800',
    borderSelected: 'border-green-400',
    resizeLine: '!border-green-300',
    resizeHandle: '!bg-green-400',
    dot: 'bg-green-300',
  },
  teal: {
    bg: 'bg-teal-50 dark:bg-teal-950/30',
    border: 'border-teal-200 dark:border-teal-800',
    borderSelected: 'border-teal-400',
    resizeLine: '!border-teal-300',
    resizeHandle: '!bg-teal-400',
    dot: 'bg-teal-300',
  },
  cyan: {
    bg: 'bg-cyan-50 dark:bg-cyan-950/30',
    border: 'border-cyan-200 dark:border-cyan-800',
    borderSelected: 'border-cyan-400',
    resizeLine: '!border-cyan-300',
    resizeHandle: '!bg-cyan-400',
    dot: 'bg-cyan-300',
  },
  blue: {
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-800',
    borderSelected: 'border-blue-400',
    resizeLine: '!border-blue-300',
    resizeHandle: '!bg-blue-400',
    dot: 'bg-blue-300',
  },
  indigo: {
    bg: 'bg-indigo-50 dark:bg-indigo-950/30',
    border: 'border-indigo-200 dark:border-indigo-800',
    borderSelected: 'border-indigo-400',
    resizeLine: '!border-indigo-300',
    resizeHandle: '!bg-indigo-400',
    dot: 'bg-indigo-300',
  },
  purple: {
    bg: 'bg-purple-50 dark:bg-purple-950/30',
    border: 'border-purple-200 dark:border-purple-800',
    borderSelected: 'border-purple-400',
    resizeLine: '!border-purple-300',
    resizeHandle: '!bg-purple-400',
    dot: 'bg-purple-300',
  },
  pink: {
    bg: 'bg-pink-50 dark:bg-pink-950/30',
    border: 'border-pink-200 dark:border-pink-800',
    borderSelected: 'border-pink-400',
    resizeLine: '!border-pink-300',
    resizeHandle: '!bg-pink-400',
    dot: 'bg-pink-300',
  },
  rose: {
    bg: 'bg-rose-50 dark:bg-rose-950/30',
    border: 'border-rose-200 dark:border-rose-800',
    borderSelected: 'border-rose-400',
    resizeLine: '!border-rose-300',
    resizeHandle: '!bg-rose-400',
    dot: 'bg-rose-300',
  },
  gray: {
    bg: 'bg-gray-50 dark:bg-gray-950/30',
    border: 'border-gray-200 dark:border-gray-700',
    borderSelected: 'border-gray-400',
    resizeLine: '!border-gray-300',
    resizeHandle: '!bg-gray-400',
    dot: 'bg-gray-300',
  },
} as const

export type CommentColor = keyof typeof COMMENT_COLORS

interface CommentNodeData {
  type: string
  label: string
  content?: string
  author?: string
  color?: CommentColor
  config: Record<string, unknown>
}

export function CommentNode({ id, selected, data }: NodeProps) {
  const nodeData = data as unknown as CommentNodeData
  const { setNodes } = useReactFlow()
  
  // 本地内容状态
  const [content, setContent] = React.useState(nodeData.content || '')
  // 编辑模式状态
  const [isEditing, setIsEditing] = React.useState(false)
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)
  
  // 当外部 data 变化时同步内容（但仅在初始化或 content 从外部更新时）
  React.useEffect(() => {
    if (nodeData.content !== undefined && nodeData.content !== content) {
      setContent(nodeData.content)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeData.content])
  
  // 进入编辑模式时聚焦
  React.useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus()
      // 光标移到末尾
      textareaRef.current.setSelectionRange(content.length, content.length)
    }
  }, [isEditing, content.length])
  
  // 颜色 - 直接从 data 读取，确保响应变化
  const colorKey = (nodeData.color || 'amber') as CommentColor
  const colors = COMMENT_COLORS[colorKey]

  // 保存内容到节点数据
  const saveContent = React.useCallback(() => {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === id
          ? {
              ...n,
              data: {
                ...n.data,
                content,
              },
            }
          : n
      )
    )
    setIsEditing(false)
  }, [id, content, setNodes])

  // 双击进入编辑模式
  const handleDoubleClick = React.useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setIsEditing(true)
  }, [])

  // 处理键盘事件
  const handleKeyDown = React.useCallback((e: React.KeyboardEvent) => {
    // Escape 退出编辑
    if (e.key === 'Escape') {
      saveContent()
    }
  }, [saveContent])

  return (
    <>
      {/* Node Resizer */}
      <NodeResizer
        minWidth={200}
        minHeight={120}
        isVisible={selected}
        lineClassName={colors.resizeLine}
        handleClassName={cn('!w-2 !h-2 !border-0 !rounded-sm', colors.resizeHandle)}
      />
      
      <div
        className={cn(
          'w-full h-full rounded-xl border shadow-sm transition-all',
          'flex flex-col',
          colors.bg,
          selected ? colors.borderSelected : colors.border
        )}
        style={{ minWidth: 200, minHeight: 120 }}
        onDoubleClick={handleDoubleClick}
      >
        {/* Content Area */}
        <div className="flex-1 p-3 overflow-auto">
          {isEditing ? (
            <textarea
              ref={textareaRef}
              className="w-full h-full bg-transparent text-foreground/80 text-sm resize-none outline-none placeholder:text-muted-foreground/50"
              placeholder="输入注释（支持 Markdown）..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onBlur={saveContent}
              onKeyDown={handleKeyDown}
            />
          ) : content ? (
            <div className="w-full h-full prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <Streamdown>{content}</Streamdown>
            </div>
          ) : (
            <span className="text-sm text-muted-foreground/50">
              双击编辑（支持 Markdown）
            </span>
          )}
        </div>
        
        {/* Footer - Author (只读显示) */}
        {nodeData.author && (
          <div className="px-3 pb-2">
            <span className="text-xs text-muted-foreground">
              {nodeData.author}
            </span>
          </div>
        )}
      </div>
    </>
  )
}
