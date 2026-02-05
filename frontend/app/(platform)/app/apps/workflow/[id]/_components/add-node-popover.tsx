'use client'

import * as React from 'react'
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

// 普通节点分类
const nodeCategories = [
  {
    label: '模型',
    nodes: [
      { type: 'llm', icon: Bot, color: 'bg-blue-500', title: 'LLM', description: '调用大语言模型' },
    ],
  },
  {
    label: '逻辑',
    nodes: [
      { type: 'condition', icon: GitBranch, color: 'bg-cyan-500', title: '条件分支', description: 'IF/ELSE 逻辑判断' },
      { type: 'question_classifier', icon: Tags, color: 'bg-violet-500', title: '问题分类', description: 'LLM 智能分类问题' },
      { type: 'iteration', icon: RefreshCw, color: 'bg-cyan-500', title: '迭代', description: '遍历数组数据' },
      { type: 'loop', icon: Infinity, color: 'bg-cyan-500', title: '循环', description: '重复执行直到满足条件' },
    ],
  },
  {
    label: '转换',
    nodes: [
      { type: 'code', icon: Code, color: 'bg-blue-500', title: '代码执行', description: '执行自定义代码' },
      { type: 'template', icon: FileText, color: 'bg-blue-500', title: '模板转换', description: '文本模板拼接' },
      { type: 'file_to_url', icon: Link, color: 'bg-teal-500', title: '文件转URL', description: '将文件/图片转为URL' },
      { type: 'variable_aggregator', icon: Combine, color: 'bg-blue-500', title: '变量聚合器', description: '聚合多个变量' },
      { type: 'variable_assignment', icon: Variable, color: 'bg-blue-500', title: '变量赋值', description: '给变量赋值' },
      { type: 'parameter_extractor', icon: Braces, color: 'bg-blue-500', title: '参数提取器', description: '从文本中提取参数' },
    ],
  },
  {
    label: '扩展',
    nodes: [
      { type: 'sub_workflow', icon: Workflow, color: 'bg-purple-500', title: '子工作流', description: '调用其他工作流' },
      { type: 'agent', icon: Sparkles, color: 'bg-indigo-500', title: '智能体', description: '调用已发布的智能体' },
      { type: 'tool', icon: Wrench, color: 'bg-emerald-500', title: '工具', description: '调用外部工具' },
      { type: 'answer', icon: MessageSquareText, color: 'bg-emerald-500', title: '输出', description: '定义工作流输出' },
    ],
  },
]

// 迭代内部节点分类
const iterationNodeCategories = [
  {
    label: '模型',
    nodes: [
      { type: 'llm', icon: Bot, color: 'bg-blue-500', title: 'LLM', description: '调用大语言模型' },
    ],
  },
  {
    label: '逻辑',
    nodes: [
      { type: 'condition', icon: GitBranch, color: 'bg-cyan-500', title: '条件分支', description: 'IF/ELSE 逻辑判断' },
      { type: 'question_classifier', icon: Tags, color: 'bg-violet-500', title: '问题分类', description: 'LLM 智能分类问题' },
      { type: 'iteration_exit', icon: LogOut, color: 'bg-orange-500', title: '退出迭代', description: '提前退出迭代' },
    ],
  },
  {
    label: '转换',
    nodes: [
      { type: 'code', icon: Code, color: 'bg-blue-500', title: '代码执行', description: '执行自定义代码' },
      { type: 'template', icon: FileText, color: 'bg-blue-500', title: '模板转换', description: '文本模板拼接' },
      { type: 'file_to_url', icon: Link, color: 'bg-teal-500', title: '文件转URL', description: '将文件/图片转为URL' },
      { type: 'variable_aggregator', icon: Combine, color: 'bg-blue-500', title: '变量聚合器', description: '聚合多个变量' },
      { type: 'variable_assignment', icon: Variable, color: 'bg-blue-500', title: '变量赋值', description: '给变量赋值' },
      { type: 'parameter_extractor', icon: Braces, color: 'bg-blue-500', title: '参数提取器', description: '从文本中提取参数' },
    ],
  },
  {
    label: '扩展',
    nodes: [
      { type: 'sub_workflow', icon: Workflow, color: 'bg-purple-500', title: '子工作流', description: '调用其他工作流' },
      { type: 'agent', icon: Sparkles, color: 'bg-indigo-500', title: '智能体', description: '调用已发布的智能体' },
      { type: 'tool', icon: Wrench, color: 'bg-emerald-500', title: '工具', description: '调用外部工具' },
    ],
  },
]

// 循环内部节点分类
const loopNodeCategories = [
  {
    label: '模型',
    nodes: [
      { type: 'llm', icon: Bot, color: 'bg-blue-500', title: 'LLM', description: '调用大语言模型' },
    ],
  },
  {
    label: '逻辑',
    nodes: [
      { type: 'condition', icon: GitBranch, color: 'bg-cyan-500', title: '条件分支', description: 'IF/ELSE 逻辑判断' },
      { type: 'question_classifier', icon: Tags, color: 'bg-violet-500', title: '问题分类', description: 'LLM 智能分类问题' },
      { type: 'loop_exit', icon: LogOut, color: 'bg-orange-500', title: '退出循环', description: '提前退出循环' },
    ],
  },
  {
    label: '转换',
    nodes: [
      { type: 'code', icon: Code, color: 'bg-blue-500', title: '代码执行', description: '执行自定义代码' },
      { type: 'template', icon: FileText, color: 'bg-blue-500', title: '模板转换', description: '文本模板拼接' },
      { type: 'file_to_url', icon: Link, color: 'bg-teal-500', title: '文件转URL', description: '将文件/图片转为URL' },
      { type: 'variable_aggregator', icon: Combine, color: 'bg-blue-500', title: '变量聚合器', description: '聚合多个变量' },
      { type: 'variable_assignment', icon: Variable, color: 'bg-blue-500', title: '变量赋值', description: '给变量赋值' },
      { type: 'parameter_extractor', icon: Braces, color: 'bg-blue-500', title: '参数提取器', description: '从文本中提取参数' },
    ],
  },
  {
    label: '扩展',
    nodes: [
      { type: 'sub_workflow', icon: Workflow, color: 'bg-purple-500', title: '子工作流', description: '调用其他工作流' },
      { type: 'agent', icon: Sparkles, color: 'bg-indigo-500', title: '智能体', description: '调用已发布的智能体' },
      { type: 'tool', icon: Wrench, color: 'bg-emerald-500', title: '工具', description: '调用外部工具' },
    ],
  },
]

export function AddNodePopover({ position, sourceNodeId, sourceHandleId, isInsideIteration, isInsideLoop, onSelect, onClose }: AddNodePopoverProps) {
  const popoverRef = React.useRef<HTMLDivElement>(null)
  const [adjustedPosition, setAdjustedPosition] = React.useState(position)
  
  // 根据是否在容器内选择节点分类
  const categories = isInsideIteration 
    ? iterationNodeCategories 
    : isInsideLoop 
      ? loopNodeCategories 
      : nodeCategories

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
        {categories.map((category) => (
          <div key={category.label}>
            <p className="text-[10px] text-muted-foreground px-2 py-1">{category.label}</p>
            <div className="space-y-0.5">
              {category.nodes.map((node) => {
                const Icon = node.icon
                return (
                  <button
                    key={node.type}
                    onClick={() => onSelect(node.type, sourceNodeId, sourceHandleId)}
                    className={cn(
                      'w-full flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer',
                      'hover:bg-accent transition-colors text-left'
                    )}
                  >
                    <div className={cn('flex h-6 w-6 items-center justify-center rounded-md text-white shrink-0', node.color)}>
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-sm truncate">{node.title}</span>
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
