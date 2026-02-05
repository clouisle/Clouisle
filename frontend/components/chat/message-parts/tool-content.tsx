'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import {
  Wrench,
  Server,
  ChevronDown,
  Check,
  X,
  Loader2,
  Clock,
} from 'lucide-react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type {
  ToolCallPart,
  ToolResultPart,
  McpToolCallPart,
  McpToolResultPart,
} from '../types'

type ToolPart = ToolCallPart | ToolResultPart | McpToolCallPart | McpToolResultPart

export interface ToolContentProps {
  part: ToolPart
  className?: string
  /** Is this an MCP tool */
  isMcp?: boolean
  /** Default open state */
  defaultOpen?: boolean
}

function getToolState(part: ToolPart) {
  if ('state' in part) {
    return part.state
  }
  if ('output' in part) {
    return part.isError ? 'error' : 'done'
  }
  return 'pending'
}

function getToolName(part: ToolPart) {
  // Prefer display name if available
  if ('toolDisplayName' in part && part.toolDisplayName) {
    return part.toolDisplayName
  }
  return part.toolName
}

function getServerName(part: ToolPart): string | undefined {
  if ('serverName' in part) {
    return part.serverName
  }
  return undefined
}

export function ToolContent({
  part,
  className,
  isMcp = false,
  defaultOpen = false,
}: ToolContentProps) {
  const t = useTranslations('chat.tool')
  const [isOpen, setIsOpen] = React.useState(defaultOpen)
  const state = getToolState(part)
  const toolName = getToolName(part)
  const serverName = getServerName(part)
  const isCall = part.type === 'tool-call' || part.type === 'mcp-tool-call'
  const isResult = part.type === 'tool-result' || part.type === 'mcp-tool-result'

  const StateIcon = {
    pending: Clock,
    running: Loader2,
    done: Check,
    error: X,
  }[state || 'pending']

  const stateColor = {
    pending: 'text-muted-foreground',
    running: 'text-blue-500',
    done: 'text-green-500',
    error: 'text-red-500',
  }[state || 'pending']

  const getStatusText = () => {
    if (state === 'running') return t('running')
    if (state === 'error') return t('error')
    if (state === 'done') return t('completed')
    return t('pending')
  }

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className={cn(
        'rounded-lg border bg-muted/30',
        state === 'error' && 'border-red-500/30 bg-red-50/30 dark:bg-red-950/20',
        className
      )}
    >
      <CollapsibleTrigger className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-muted/50 transition-colors rounded-lg">
        {/* Icon */}
        <div
          className={cn(
            'flex items-center justify-center w-6 h-6 rounded-md',
            isMcp ? 'bg-purple-100 dark:bg-purple-900/30' : 'bg-orange-100 dark:bg-orange-900/30'
          )}
        >
          {isMcp ? (
            <Server className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400" />
          ) : (
            <Wrench className="h-3.5 w-3.5 text-orange-600 dark:text-orange-400" />
          )}
        </div>

        {/* Tool info */}
        <div className="flex-1 text-left">
          <div className="flex items-center gap-1.5">
            <span className="font-medium">{toolName}</span>
            {serverName && (
              <span className="text-xs text-muted-foreground">
                @ {serverName}
              </span>
            )}
          </div>
        </div>

        {/* State indicator */}
        <div className={cn('flex items-center gap-1.5 text-xs', stateColor)}>
          <StateIcon
            className={cn('h-3.5 w-3.5', state === 'running' && 'animate-spin')}
          />
          <span>{getStatusText()}</span>
        </div>

        <ChevronDown
          className={cn(
            'h-4 w-4 text-muted-foreground transition-transform',
            isOpen && 'rotate-180'
          )}
        />
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="px-3 pb-3 space-y-2">
          {/* Input */}
          {isCall && 'input' in part && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('input')}
              </div>
              <pre className="text-xs bg-muted/50 rounded-md p-2 overflow-x-auto max-h-40">
                {JSON.stringify(part.input, null, 2)}
              </pre>
            </div>
          )}

          {/* Output */}
          {isResult && 'output' in part && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('output')}
              </div>
              <pre
                className={cn(
                  'text-xs rounded-md p-2 overflow-x-auto max-h-40',
                  part.isError
                    ? 'bg-red-100/50 dark:bg-red-950/30 text-red-700 dark:text-red-300'
                    : 'bg-muted/50'
                )}
              >
                {typeof part.output === 'string'
                  ? part.output
                  : JSON.stringify(part.output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
