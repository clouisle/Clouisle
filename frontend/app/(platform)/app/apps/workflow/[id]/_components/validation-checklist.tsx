'use client'

import * as React from 'react'
import { X, AlertTriangle, XCircle, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'
import { ValidationIssue, getNodeTypeColor } from './workflow-validator'
import {
  Bot,
  MessageSquareText,
  Tags,
  GitBranch,
  Code2,
  FileText,
  Wrench,
  ListFilter,
  LayoutList,
  Variable,
  Repeat,
  RotateCcw,
  GitFork,
  FileInput,
  Zap,
} from 'lucide-react'

// 节点类型图标映射
const nodeTypeIcons: Record<string, React.ElementType> = {
  user_input: FileInput,
  trigger: Zap,
  llm: Bot,
  condition: GitBranch,
  question_classifier: Tags,
  answer: MessageSquareText,
  tool: Wrench,
  code: Code2,
  template: FileText,
  parameter_extractor: ListFilter,
  variable_aggregator: LayoutList,
  variable_assignment: Variable,
  iteration: Repeat,
  loop: RotateCcw,
  sub_workflow: GitFork,
}

interface ValidationChecklistProps {
  issues: ValidationIssue[]
  onClose: () => void
  onSelectNode: (nodeId: string) => void
}

export function ValidationChecklist({ issues, onClose, onSelectNode }: ValidationChecklistProps) {
  const t = useTranslations('workflow')
  const errorCount = issues.filter(i => i.severity === 'error').length
  const warningCount = issues.filter(i => i.severity === 'warning').length

  // 按节点分组
  const issuesByNode = React.useMemo(() => {
    const grouped = new Map<string, ValidationIssue[]>()
    for (const issue of issues) {
      const existing = grouped.get(issue.nodeId) || []
      existing.push(issue)
      grouped.set(issue.nodeId, existing)
    }
    return grouped
  }, [issues])

  return (
    <div className="w-80 bg-card border border-border rounded-xl shadow-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-sm">{t('checklist.title')}</h3>
          <span className="text-xs text-muted-foreground">({issues.length})</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>

      {/* Description */}
      <div className="px-4 py-2 border-b border-border bg-muted/30">
        <p className="text-xs text-muted-foreground">
          {t('checklist.description')}
        </p>
      </div>

      {/* Issues List */}
      <div className="max-h-100 overflow-y-auto">
        {issues.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center mb-3">
              <svg className="w-6 h-6 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-sm font-medium">{t('checklist.allPassed')}</p>
            <p className="text-xs mt-1">{t('checklist.readyToPublish')}</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {Array.from(issuesByNode.entries()).map(([nodeId, nodeIssues]) => {
              const firstIssue = nodeIssues[0]
              const NodeIcon = nodeTypeIcons[firstIssue.nodeType] || Bot
              const iconBgColor = getNodeTypeColor(firstIssue.nodeType)
              const hasError = nodeIssues.some(i => i.severity === 'error')

              return (
                <div key={nodeId} className="p-3">
                  {/* Node Header */}
                  <button
                    onClick={() => nodeId !== 'workflow' && onSelectNode(nodeId)}
                    className={cn(
                      'w-full flex items-center gap-2 p-2 rounded-lg transition-colors',
                      nodeId !== 'workflow' && 'hover:bg-accent cursor-pointer'
                    )}
                  >
                    {/* Node Icon */}
                    <div className={cn(
                      'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-white',
                      iconBgColor
                    )}>
                      <NodeIcon className="h-3.5 w-3.5" />
                    </div>
                    
                    {/* Node Name */}
                    <span className="flex-1 text-sm font-medium text-left truncate">
                      {firstIssue.nodeLabel !== firstIssue.nodeType ? firstIssue.nodeLabel : t(firstIssue.nodeLabelKey)}
                    </span>

                    {/* Navigate Icon */}
                    {nodeId !== 'workflow' && (
                      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                  </button>

                  {/* Issues for this node */}
                  <div className="mt-1 ml-9 space-y-1">
                    {nodeIssues.map((issue) => (
                      <div
                        key={issue.id}
                        className={cn(
                          'flex items-start gap-2 px-2 py-1.5 rounded-md text-xs',
                          issue.severity === 'error' 
                            ? 'bg-red-500/10 text-red-600 dark:text-red-400' 
                            : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                        )}
                      >
                        {issue.severity === 'error' ? (
                          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        ) : (
                          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        )}
                        <span>{t(issue.messageKey, issue.messageParams)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Footer Summary */}
      {issues.length > 0 && (
        <div className="px-4 py-2 border-t border-border bg-muted/30 flex items-center gap-4 text-xs">
          {errorCount > 0 && (
            <span className="flex items-center gap-1 text-red-500">
              <XCircle className="h-3.5 w-3.5" />
              {t('checklist.errorCount', { count: errorCount })}
            </span>
          )}
          {warningCount > 0 && (
            <span className="flex items-center gap-1 text-amber-500">
              <AlertTriangle className="h-3.5 w-3.5" />
              {t('checklist.warningCount', { count: warningCount })}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
