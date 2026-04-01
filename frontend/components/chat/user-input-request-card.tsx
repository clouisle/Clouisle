'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'
import { MessageCircleQuestion } from 'lucide-react'
import { Button } from '@/components/ui/button'

export interface UserInputRequestCardProps {
  question: string
  options: string[]
  state?: 'pending' | 'answered'
  selectedOption?: string
  onSelectOption?: (option: string) => void
  /** Whether the message is currently streaming (disables interaction) */
  isStreaming?: boolean
  className?: string
}

export function UserInputRequestCard({
  question,
  options,
  state = 'pending',
  selectedOption,
  onSelectOption,
  isStreaming = false,
  className,
}: UserInputRequestCardProps) {
  const [localState, setLocalState] = React.useState<'pending' | 'answered'>(state)
  const [localSelectedOption, setLocalSelectedOption] = React.useState<string | undefined>(selectedOption)

  // Sync with props
  React.useEffect(() => {
    setLocalState(state)
  }, [state])

  React.useEffect(() => {
    setLocalSelectedOption(selectedOption)
  }, [selectedOption])

  const isPending = localState === 'pending'
  // Disable interaction if streaming or already answered
  const isInteractive = isPending && !isStreaming

  const handleSelectOption = (option: string) => {
    if (!isInteractive) return

    // Immediately update local state to prevent multiple clicks
    setLocalState('answered')
    setLocalSelectedOption(option)

    // Call the callback
    onSelectOption?.(option)
  }

  return (
    <div
      className={cn(
        'w-full max-w-full min-w-0 rounded-lg border bg-muted/50 p-4 space-y-3',
        className
      )}
    >
      {/* Question */}
      <div className="flex items-start gap-2">
        <MessageCircleQuestion className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
        <p className="min-w-0 whitespace-pre-wrap break-words text-sm font-medium leading-6">
          {question}
        </p>
      </div>

      {/* Options */}
      <div className="grid gap-2">
        {options.map((option, index) => {
          const isSelected = localSelectedOption === option

          return (
            <Button
              key={index}
              variant={isSelected ? 'default' : 'outline'}
              size="sm"
              className={cn(
                'h-auto w-full min-w-0 justify-start px-3 py-2 text-left !whitespace-normal break-words leading-6',
                isInteractive && 'hover:bg-primary/10 hover:border-primary/50 transition-colors cursor-pointer',
                !isInteractive && !isSelected && 'opacity-50 cursor-not-allowed',
                isSelected && 'bg-primary text-primary-foreground'
              )}
              disabled={!isInteractive}
              onClick={() => handleSelectOption(option)}
            >
              {option}
            </Button>
          )
        })}
      </div>

      {/* Helper text */}
      {isInteractive && (
        <p className="text-xs text-muted-foreground">
          Click an option above or type your own response
        </p>
      )}
      {isStreaming && isPending && (
        <p className="text-xs text-muted-foreground">
          Waiting for response to complete...
        </p>
      )}
    </div>
  )
}
