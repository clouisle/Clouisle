import { cn } from '@/lib/utils'
import type { ExecutionState } from '@/components/chat/types'
import { NodeCard } from './node-card'

interface ExecutionTimelineProps {
  executionState: ExecutionState
  layout?: 'horizontal' | 'vertical'
  showDetails?: boolean
}

export function ExecutionTimeline({
  executionState,
  layout = 'vertical',
  showDetails = true,
}: ExecutionTimelineProps) {
  const nodes = Array.from(executionState.nodes.values())

  if (nodes.length === 0) {
    return null
  }

  return (
    <div className="space-y-3">
      {/* Progress indicator */}
      {executionState.progress.total > 0 && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Progress</span>
            <span>
              {executionState.progress.current} / {executionState.progress.total}
            </span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{
                width: `${(executionState.progress.current / executionState.progress.total) * 100}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Node list */}
      <div
        className={cn(
          'space-y-2',
          layout === 'horizontal' && 'flex gap-2 overflow-x-auto'
        )}
      >
        {nodes.map((node) => (
          <NodeCard key={node.id} node={node} compact={!showDetails} />
        ))}
      </div>
    </div>
  )
}
