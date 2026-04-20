import { cn } from '@/lib/utils'
import type { ExecutionNode } from '@/components/chat/types'
import { CheckCircle2, Circle, Loader2, XCircle, SkipForward } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

interface NodeCardProps {
  node: ExecutionNode
  compact?: boolean
}

export function NodeCard({ node, compact = false }: NodeCardProps) {
  const tCommon = useTranslations('common')
  const tTool = useTranslations('chat.tool')
  const [isOpen, setIsOpen] = useState(false)

  const statusConfig: Record<string, {
    icon: React.ComponentType<{ className?: string }>
    color: string
    bgColor: string
    animate?: boolean
  }> = {
    pending: {
      icon: Circle,
      color: 'text-muted-foreground',
      bgColor: 'bg-muted',
    },
    running: {
      icon: Loader2,
      color: 'text-blue-500',
      bgColor: 'bg-blue-50 dark:bg-blue-950',
      animate: true,
    },
    completed: {
      icon: CheckCircle2,
      color: 'text-green-500',
      bgColor: 'bg-green-50 dark:bg-green-950',
    },
    error: {
      icon: XCircle,
      color: 'text-red-500',
      bgColor: 'bg-red-50 dark:bg-red-950',
    },
    skipped: {
      icon: SkipForward,
      color: 'text-muted-foreground',
      bgColor: 'bg-muted',
    },
  }

  const config = statusConfig[node.status]
  const StatusIcon = config.icon

  const hasDetails = !compact && (node.input || node.output || node.error)

  return (
    <div
      className={cn(
        'rounded-lg border p-3 transition-colors',
        config.bgColor
      )}
    >
      <div className="flex items-center gap-2">
        <StatusIcon
          className={cn('h-4 w-4', config.color, config.animate && 'animate-spin')}
        />
        <span className="font-medium text-sm flex-1">{node.label}</span>
        {node.duration !== undefined && (
          <span className="text-xs text-muted-foreground">
            {node.duration}ms
          </span>
        )}
      </div>

      {node.error && (
        <div className="mt-2 text-xs text-red-600 dark:text-red-400">
          {node.error}
        </div>
      )}

      {hasDetails && (
        <Collapsible open={isOpen} onOpenChange={setIsOpen} className="mt-2">
          <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <ChevronDown
              className={cn(
                'h-3 w-3 transition-transform',
                isOpen && 'rotate-180'
              )}
            />
            {isOpen ? tCommon('hideDetails') : tCommon('showDetails')}
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 space-y-2">
            {node.input !== undefined && node.input !== null && (
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  {tTool('input')}
                </div>
                <pre className="text-xs bg-background/50 rounded p-2 overflow-x-auto">
                  {JSON.stringify(node.input, null, 2)}
                </pre>
              </div>
            )}
            {node.output !== undefined && node.output !== null && !node.error && (
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  {tTool('output')}
                </div>
                <pre className="text-xs bg-background/50 rounded p-2 overflow-x-auto">
                  {typeof node.output === 'string'
                    ? node.output
                    : JSON.stringify(node.output, null, 2)}
                </pre>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
