'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Bot, GitBranch, Workflow, Wrench, Code, X, RefreshCw, Infinity, LogOut, FileText, Combine, Variable, Braces, Link, Tags, MessageSquareText, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AddNodePopoverProps {
  position: { x: number; y: number }
  sourceNodeId: string
  sourceHandleId?: string
  isInsideIteration?: boolean
  isInsideLoop?: boolean
  onSelect: (type: string, sourceNodeId: string, sourceHandleId?: string) => void
  onClose: () => void
}

// Node definitions without labels (labels come from i18n)
const nodeDefinitions: Record<string, { icon: React.ElementType; color: string }> = {
  llm: { icon: Bot, color: 'bg-blue-500' },
  condition: { icon: GitBranch, color: 'bg-cyan-500' },
  question_classifier: { icon: Tags, color: 'bg-violet-500' },
  iteration: { icon: RefreshCw, color: 'bg-cyan-500' },
  loop: { icon: Infinity, color: 'bg-cyan-500' },
  iteration_exit: { icon: LogOut, color: 'bg-orange-500' },
  loop_exit: { icon: LogOut, color: 'bg-orange-500' },
  code: { icon: Code, color: 'bg-blue-500' },
  template: { icon: FileText, color: 'bg-blue-500' },
  file_to_url: { icon: Link, color: 'bg-teal-500' },
  variable_aggregator: { icon: Combine, color: 'bg-blue-500' },
  variable_assignment: { icon: Variable, color: 'bg-blue-500' },
  parameter_extractor: { icon: Braces, color: 'bg-blue-500' },
  sub_workflow: { icon: Workflow, color: 'bg-purple-500' },
  agent: { icon: Sparkles, color: 'bg-indigo-500' },
  tool: { icon: Wrench, color: 'bg-emerald-500' },
  answer: { icon: MessageSquareText, color: 'bg-emerald-500' },
}

// Category structure definitions (type references only)
type CategoryDef = { labelKey: string; nodeTypes: string[] }

const normalCategories: CategoryDef[] = [
  { labelKey: 'model', nodeTypes: ['llm'] },
  { labelKey: 'logic', nodeTypes: ['condition', 'question_classifier', 'iteration', 'loop'] },
  { labelKey: 'transform', nodeTypes: ['code', 'template', 'file_to_url', 'variable_aggregator', 'variable_assignment', 'parameter_extractor'] },
  { labelKey: 'extension', nodeTypes: ['sub_workflow', 'agent', 'tool', 'answer'] },
]

const iterationCategories: CategoryDef[] = [
  { labelKey: 'model', nodeTypes: ['llm'] },
  { labelKey: 'logic', nodeTypes: ['condition', 'question_classifier', 'iteration_exit'] },
  { labelKey: 'transform', nodeTypes: ['code', 'template', 'file_to_url', 'variable_aggregator', 'variable_assignment', 'parameter_extractor'] },
  { labelKey: 'extension', nodeTypes: ['sub_workflow', 'agent', 'tool'] },
]

const loopCategories: CategoryDef[] = [
  { labelKey: 'model', nodeTypes: ['llm'] },
  { labelKey: 'logic', nodeTypes: ['condition', 'question_classifier', 'loop_exit'] },
  { labelKey: 'transform', nodeTypes: ['code', 'template', 'file_to_url', 'variable_aggregator', 'variable_assignment', 'parameter_extractor'] },
  { labelKey: 'extension', nodeTypes: ['sub_workflow', 'agent', 'tool'] },
]

export function AddNodePopover({ position, sourceNodeId, sourceHandleId, isInsideIteration, isInsideLoop, onSelect, onClose }: AddNodePopoverProps) {
  const t = useTranslations('workflow')
  const popoverRef = React.useRef<HTMLDivElement>(null)
  const [adjustedPosition, setAdjustedPosition] = React.useState(position)

  // 根据是否在容器内选择节点分类
  const categoryDefs = isInsideIteration
    ? iterationCategories
    : isInsideLoop
      ? loopCategories
      : normalCategories

  // 调整位置确保不超出屏幕
  React.useEffect(() => {
    if (!popoverRef.current) return
    
    const popover = popoverRef.current
    const rect = popover.getBoundingClientRect()
    const padding = 16 // 距离屏幕边缘的最小间距
    
    let newX = position.x
    let newY = position.y
    
    // 检查右边界
    if (position.x + rect.width + padding > window.innerWidth) {
      // 如果右边超出，放到左边
      newX = position.x - rect.width - 16
    }
    
    // 检查左边界
    if (newX < padding) {
      newX = padding
    }
    
    // 检查底部边界（考虑 transform: translate(0, -50%)）
    const halfHeight = rect.height / 2
    if (position.y + halfHeight + padding > window.innerHeight) {
      newY = window.innerHeight - halfHeight - padding
    }
    
    // 检查顶部边界
    if (position.y - halfHeight < padding) {
      newY = halfHeight + padding
    }
    
    if (newX !== position.x || newY !== position.y) {
      setAdjustedPosition({ x: newX, y: newY })
    } else {
      setAdjustedPosition(position)
    }
  }, [position])

  // Close when clicking outside
  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    
    // Use setTimeout to avoid immediate close
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside)
    }, 0)
    
    return () => {
      clearTimeout(timer)
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [onClose])

  // Close on escape
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div
      ref={popoverRef}
      className="fixed z-50 w-44 rounded-lg border border-border bg-card shadow-xl animate-in fade-in-0 zoom-in-95"
      style={{
        left: adjustedPosition.x,
        top: adjustedPosition.y,
        transform: adjustedPosition.x !== position.x ? 'translate(-100%, -50%)' : 'translate(8px, -50%)',
      }}
    >
      {/* 关闭按钮 */}
      <button
        onClick={onClose}
        className="absolute -top-2 -right-2 p-1 rounded-full bg-card border border-border hover:bg-muted transition-colors shadow-sm cursor-pointer"
      >
        <X className="h-3 w-3 text-muted-foreground" />
      </button>
      <div className="p-2 space-y-2 max-h-[400px] overflow-y-auto">
        {categoryDefs.map((category) => (
          <div key={category.labelKey}>
            <p className="text-[10px] text-muted-foreground px-2 py-1">{t(`nodeCategories.${category.labelKey}`)}</p>
            <div className="space-y-0.5">
              {category.nodeTypes.map((nodeType) => {
                const def = nodeDefinitions[nodeType]
                if (!def) return null
                const Icon = def.icon
                return (
                  <button
                    key={nodeType}
                    onClick={() => onSelect(nodeType, sourceNodeId, sourceHandleId)}
                    className={cn(
                      'w-full flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer',
                      'hover:bg-accent transition-colors text-left'
                    )}
                  >
                    <div className={cn('flex h-6 w-6 items-center justify-center rounded-md text-white shrink-0', def.color)}>
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-sm truncate">{t(`nodeLabels.${nodeType}`)}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
