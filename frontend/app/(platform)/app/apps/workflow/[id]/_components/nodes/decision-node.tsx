'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { GitBranch } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

import { getDecisionOutputHandles } from './decision-branch-handles'
export type DecisionQuestionType = 'choice' | 'score' | 'noul'

export interface DecisionNodeConfig {
  modelId?: string
  modelName?: string
  stateTemplate: string
  questionId: string
  questionType: DecisionQuestionType
  instructions: string
  options: string[]
  defaultHandle?: string
  confidenceThreshold?: number
}

export const defaultDecisionNodeConfig: DecisionNodeConfig = {
  stateTemplate: '',
  questionId: 'decision',
  questionType: 'choice',
  instructions: '',
  options: ['yes', 'no'],
  defaultHandle: 'default',
}

interface DecisionNodeProps {
  selected?: boolean
  data: { label?: string; decisionConfig?: DecisionNodeConfig }
}

export function DecisionNode({ selected, data }: DecisionNodeProps) {
  const t = useTranslations('workflow')
  const config = { ...defaultDecisionNodeConfig, ...data.decisionConfig }
  const handles = getDecisionOutputHandles(config)
  const promptLines = [config.stateTemplate, config.instructions]
    .map((line) => line?.trim())
    .filter((line): line is string => !!line)

  return (
    <div className="group relative min-w-[190px]">
      <div
        className={cn(
          'relative rounded-xl border bg-card px-2.5 py-2 shadow-sm',
          selected ? 'border-primary' : 'border-border hover:border-primary/50'
        )}
      >
        <Handle
          type="target"
          position={Position.Left}
          className="h-2! w-2! rounded-full! border-0! bg-primary!"
          style={{ top: 24 }}
        />
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-500 text-white">
            <GitBranch className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">
              {data.label || t('nodesDecision.label')}
            </span>
            <span className="block truncate text-xs text-muted-foreground">
              {config.modelName || t('nodesCommon.modelNotSelected')}
            </span>
          </div>
        </div>
        <div className="mt-1 grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2 pt-0.5">
          {promptLines.length > 0 && (
            <div className="min-w-0 self-center text-[10px] leading-4 text-muted-foreground">
              {promptLines.map((line, index) => (
                <div key={index} className="truncate" title={line}>
                  {line}
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-col gap-0.5">
            {handles.map((handle) => (
              <div
                key={handle}
                className="flex h-4 items-center justify-end pr-2 text-[10px] font-medium leading-none text-muted-foreground"
              >
                <span>{handle}</span>
              </div>
            ))}
          </div>
        </div>
        {/* Output handles positioned on the card border, centered on each compact row. */}
        {handles.map((handle, index) => {
          // Header is ~44px; list offset is 6px; rows are 16px with a 2px gap.
          const top = 44 + 6 + index * 18 + 8
          return (
            <Handle
              key={handle}
              type="source"
              id={handle}
              position={Position.Right}
              className="h-2! w-2! rounded-full! border-0! bg-violet-500!"
              style={{ top }}
            />
          )
        })}
      </div>
    </div>
  )
}
