'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import { Brain, ChevronDown, Loader2 } from 'lucide-react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type { ReasoningPart } from '../types'

export interface ReasoningContentProps {
  part: ReasoningPart
  className?: string
  /** Default open state */
  defaultOpen?: boolean
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}m ${remainingSeconds}s`
}

export function ReasoningContent({
  part,
  className,
  defaultOpen = false,
}: ReasoningContentProps) {
  const t = useTranslations('chat.reasoning')
  const [isOpen, setIsOpen] = React.useState(defaultOpen)
  const isStreaming = part.state === 'streaming'

  // Auto-open when streaming
  React.useEffect(() => {
    if (isStreaming) {
      setIsOpen(true)
    }
  }, [isStreaming])

  const getStatusText = () => {
    if (isStreaming) {
      return t('thinking')
    }
    if (part.duration) {
      return t('thoughtFor', { seconds: formatDuration(part.duration) })
    }
    return t('thought')
  }

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className={cn(
        'rounded-lg border bg-muted/30',
        className
      )}
    >
      <CollapsibleTrigger className="flex items-center gap-2 w-full px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
        {isStreaming ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        ) : (
          <Brain className="h-4 w-4 text-primary" />
        )}
        <span className="flex-1 text-left">{getStatusText()}</span>
        <ChevronDown
          className={cn(
            'h-4 w-4 transition-transform',
            isOpen && 'rotate-180'
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pb-3 pt-1 text-sm text-muted-foreground whitespace-pre-wrap break-all max-h-64 overflow-y-auto">
          {part.text || t('processing')}
          {isStreaming && (
            <span className="inline-block w-1 h-3 ml-0.5 bg-current animate-blink" />
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
