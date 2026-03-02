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
  className?: string
}

export function UserInputRequestCard({
  question,
  options,
  state = 'pending',
  selectedOption,
  onSelectOption,
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

  const handleSelectOption = (option: string) => {
    if (!isPending) return

    // Immediately update local state to prevent multiple clicks
    setLocalState('answered')
    setLocalSelectedOption(option)

    // Call the callback
    onSelectOption?.(option)
  }

  return (
    <div
      className={cn(
        'rounded-lg border bg-muted/50 p-4 space-y-3',
        className
      )}
    >
      {/* Question */}
      <div className="flex items-start gap-2">
        <MessageCircleQuestion className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
        <p className="text-sm font-medium">{question}</p>
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
                'justify-start text-left h-auto py-2 px-3 whitespace-normal',
                isPending && 'hover:bg-primary/10 hover:border-primary/50 transition-colors cursor-pointer',
                !isPending && !isSelected && 'opacity-50 cursor-default',
                isSelected && 'bg-primary text-primary-foreground'
              )}
              disabled={!isPending}
              onClick={() => handleSelectOption(option)}
            >
              {option}
            </Button>
          )
        })}
      </div>

      {/* Helper text */}
      {isPending && (
        <p className="text-xs text-muted-foreground">
          Click an option above or type your own response
        </p>
      )}
    </div>
  )
}
