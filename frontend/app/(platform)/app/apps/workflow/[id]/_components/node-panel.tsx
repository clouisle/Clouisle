'use client'

import * as React from 'react'
import { Bot, GitBranch, Workflow, Wrench, Code } from 'lucide-react'
import { cn } from '@/lib/utils'

interface NodePanelProps {
  onAddNode: (type: string) => void
}

const nodeTypes = [
  { type: 'llm', icon: Bot, color: 'bg-blue-500', title: 'LLM', description: '调用大语言模型' },
  { type: 'condition', icon: GitBranch, color: 'bg-orange-500', title: '条件分支', description: 'IF/ELSE 逻辑判断' },
  { type: 'sub_workflow', icon: Workflow, color: 'bg-purple-500', title: '子工作流', description: '调用其他工作流' },
  { type: 'tool', icon: Wrench, color: 'bg-emerald-500', title: '工具', description: '调用外部工具' },
  { type: 'code', icon: Code, color: 'bg-gray-500', title: '代码', description: '执行自定义代码' },
]

export function NodePanel({ onAddNode }: NodePanelProps) {
  return (
    <div className="absolute left-4 top-4 z-10 w-[200px] rounded-xl border border-border bg-card shadow-lg">
      <div className="p-3 border-b border-border">
        <h3 className="text-sm font-medium">添加节点</h3>
        <p className="text-xs text-muted-foreground">拖拽或点击添加</p>
      </div>
      <div className="p-2 space-y-1">
        {nodeTypes.map((node) => {
          const Icon = node.icon
          return (
            <button
              key={node.type}
              onClick={() => onAddNode(node.type)}
              className={cn(
                'w-full flex items-center gap-3 p-2 rounded-lg',
                'hover:bg-accent transition-colors text-left'
              )}
            >
              <div className={cn('flex h-8 w-8 items-center justify-center rounded-lg text-white shrink-0', node.color)}>
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{node.title}</p>
                <p className="text-xs text-muted-foreground truncate">{node.description}</p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
